import contextlib
import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .splitter import body_hash


def now():
    return datetime.now(timezone.utc).isoformat()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        for folder in ('sources', 'pages', 'exports'):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'pdf-import.sqlite3'
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,name TEXT NOT NULL,pages INTEGER NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,source_id TEXT NOT NULL,pages TEXT NOT NULL,chapter TEXT NOT NULL,status TEXT NOT NULL,progress INTEGER NOT NULL,detail TEXT NOT NULL,error TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY,batch_id TEXT NOT NULL,revision INTEGER NOT NULL,data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS draft_batch ON drafts(batch_id);
                CREATE TABLE IF NOT EXISTS bank(id TEXT PRIMARY KEY,body_hash TEXT NOT NULL,data TEXT NOT NULL,created TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS bank_body ON bank(body_hash);
                CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,created TEXT NOT NULL,kind TEXT NOT NULL,data TEXT NOT NULL);
            ''')
            db.execute("UPDATE batches SET status='interrupted',detail='上次运行中断，可继续识别。' WHERE status IN ('queued','running','cancelling')")

    @contextlib.contextmanager
    def connect(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=15)
            db.row_factory = sqlite3.Row
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    def event(self, db, kind, data):
        db.execute('INSERT INTO events VALUES(?,?,?,?)', (uuid.uuid4().hex, now(), kind, dumps(data)))

    def add_source(self, sid, name, page_count):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?)', (sid, name, page_count, now()))

    def source(self, sid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM sources WHERE id=?', (sid,)).fetchone()
        if row is None:
            raise KeyError('来源文件不存在。')
        return dict(row)

    def create_batch(self, sid, pages, chapter):
        self.source(sid)
        bid = hashlib.sha256(dumps([sid, pages, chapter, 1]).encode()).hexdigest()[:32]
        with self.connect() as db:
            existing = db.execute('SELECT id FROM batches WHERE id=?', (bid,)).fetchone()
            if not existing:
                stamp = now()
                db.execute('INSERT INTO batches VALUES(?,?,?,?,?,?,?,?,?,?)',
                           (bid, sid, dumps(pages), chapter, 'queued', 0, '等待本地识别。', '', stamp, stamp))
                self.event(db, 'create_batch', {'id': bid, 'source': sid, 'pages': pages})
        return self.batch(bid)

    def batches(self):
        with self.connect() as db:
            ids = [row['id'] for row in db.execute('SELECT id FROM batches ORDER BY created DESC')]
        return [self.batch(bid, include_drafts=False) for bid in ids]

    def batch(self, bid, include_drafts=True):
        with self.connect() as db:
            row = db.execute('SELECT * FROM batches WHERE id=?', (bid,)).fetchone()
            if row is None:
                raise KeyError('导入批次不存在。')
            batch = dict(row)
            batch['pages'] = json.loads(batch['pages'])
            batch['source'] = self.source(batch['source_id'])
            batch['draft_count'] = db.execute('SELECT count(*) FROM drafts WHERE batch_id=?', (bid,)).fetchone()[0]
            if include_drafts:
                batch['drafts'] = sorted([dict(json.loads(r['data']), id=r['id'], revision=r['revision']) for r in db.execute('SELECT * FROM drafts WHERE batch_id=? ORDER BY rowid', (bid,))], key=lambda q: q.get('_order', 0))
        return batch

    def update_batch(self, bid, **fields):
        allowed = {'status', 'progress', 'detail', 'error'}
        if not fields or not set(fields) <= allowed:
            raise ValueError('批次字段错误。')
        with self.connect() as db:
            db.execute('UPDATE batches SET ' + ','.join(f'{key}=?' for key in fields) + ',updated=? WHERE id=?', (*fields.values(), now(), bid))

    def save_drafts(self, bid, rows):
        source_id = self.batch(bid, False)['source_id']
        with self.connect() as db:
            # Recognition retries never overwrite human edits.
            if db.execute('SELECT 1 FROM drafts WHERE batch_id=? LIMIT 1', (bid,)).fetchone():
                return
            for index, row in enumerate(rows):
                row['source_id'] = source_id
                row['_order'] = index
                duplicate = db.execute('SELECT id FROM bank WHERE id=? OR body_hash=? LIMIT 1',
                                       (row['question_id'], body_hash(row['stem'], row['options']))).fetchone()
                if duplicate:
                    row['duplicate_of'] = duplicate['id']
                db.execute('INSERT INTO drafts VALUES(?,?,?,?)', (uuid.uuid4().hex, bid, 1, dumps(row)))

    def draft(self, did):
        with self.connect() as db:
            row = db.execute('SELECT * FROM drafts WHERE id=?', (did,)).fetchone()
        if row is None:
            raise KeyError('题目草稿不存在。')
        return dict(json.loads(row['data']), id=row['id'], batch_id=row['batch_id'], revision=row['revision'])

    def edit_draft(self, did, revision, fields):
        allowed = {'stem': 16000, 'answer': 30000, 'solution': 60000, 'chapter': 60, 'point': 200, 'model': 300, 'type': 10}
        if not isinstance(fields, dict) or not set(fields) <= set(allowed) | {'options', 'number', 'fragments'}:
            raise ValueError('题目字段错误。')
        for key, limit in allowed.items():
            if key in fields and (not isinstance(fields[key], str) or len(fields[key]) > limit):
                raise ValueError(f'{key}内容过长或格式错误。')
        if 'type' in fields and fields['type'] not in ('选择题', '填空题', '解答题'):
            raise ValueError('题型不支持。')
        if 'number' in fields and fields['number'] is not None and (not isinstance(fields['number'], int) or not 1 <= fields['number'] <= 999):
            raise ValueError('题号须为1至999的整数。')
        if 'options' in fields and (not isinstance(fields['options'], list) or len(fields['options']) > 4 or any(not isinstance(v, str) or len(v) > 6000 for v in fields['options'])):
            raise ValueError('选项格式错误。')
        old = self.draft(did)
        if 'fragments' in fields:
            valid_pages = set(self.batch(old['batch_id'], False)['pages'])
            if not isinstance(fields['fragments'], list) or not 1 <= len(fields['fragments']) <= 30:
                raise ValueError('原页区域格式错误。')
            for fragment in fields['fragments']:
                box = fragment.get('box', [])
                if fragment.get('page') not in valid_pages or len(box) != 4 or any(type(v) not in (int, float) for v in box) or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
                    raise ValueError('原页区域超出范围。')
        with self.connect() as db:
            row = db.execute('SELECT * FROM drafts WHERE id=?', (did,)).fetchone()
            if row['revision'] != revision:
                raise Conflict('题目已在另一处修改，请重新打开后编辑。')
            data = json.loads(row['data'])
            data.update(fields)
            data['status'] = 'pending'
            data['math_verified'] = False
            db.execute('UPDATE drafts SET revision=revision+1,data=? WHERE id=?', (dumps(data), did))
            self.event(db, 'edit_draft', {'id': did, 'revision': revision + 1})
        return self.draft(did)

    def split_draft(self, did, revision, offset):
        with self.connect() as db:
            row = db.execute('SELECT * FROM drafts WHERE id=?', (did,)).fetchone()
            if not row:
                raise KeyError('题目不存在。')
            if row['revision'] != revision:
                raise Conflict('题目已修改，请重新打开后拆分。')
            data = json.loads(row['data'])
            if data['status'] == 'merged' or type(offset) is not int or not 0 < offset < len(data['stem']):
                raise ValueError('请将光标放在题干中间的拆题位置。')
            if not data['stem'][:offset].strip() or not data['stem'][offset:].strip():
                raise ValueError('拆分后的两道题都需要有题干。')
            original = json.loads(row['data'])
            next_orders = [json.loads(r['data']).get('_order', 0) for r in db.execute('SELECT data FROM drafts WHERE batch_id=?', (row['batch_id'],))]
            order = data.get('_order', 0)
            following = min((v for v in next_orders if v > order), default=order + 1)
            second = dict(data, stem=data['stem'][offset:].strip(), number=None, options=[], answer='', solution='',
                          status='pending', math_verified=False, _order=(order + following) / 2,
                          question_id='PDF-' + uuid.uuid4().hex[:24])
            data.update(stem=data['stem'][:offset].strip(), status='pending', math_verified=False)
            for item in (data, second):
                item['issues'] = list(item['issues']) + ['手动拆分：选项和答案仍保留在前一题，请重新分配；两题原页区域需核对。']
                item.pop('duplicate_of', None)
            new_id = uuid.uuid4().hex
            db.execute('UPDATE drafts SET revision=revision+1,data=? WHERE id=?', (dumps(data), did))
            db.execute('INSERT INTO drafts VALUES(?,?,?,?)', (new_id, row['batch_id'], 1, dumps(second)))
            self.event(db, 'split_draft', {'id': did, 'new_id': new_id, 'before': original})
        return self.draft(did)

    def merge_draft(self, did, revision, next_id, next_revision):
        with self.connect() as db:
            rows = [db.execute('SELECT * FROM drafts WHERE id=?', (key,)).fetchone() for key in (did, next_id)]
            if not all(rows):
                raise KeyError('题目不存在。')
            left, right = rows
            if left['revision'] != revision or right['revision'] != next_revision:
                raise Conflict('题目已修改，请重新打开后合并。')
            if did == next_id or left['batch_id'] != right['batch_id']:
                raise ValueError('只能合并同一批次的相邻题目。')
            active = [q['id'] for q in self.batch(left['batch_id'])['drafts'] if q['status'] != 'merged']
            if did not in active or active.index(did) + 1 >= len(active) or active[active.index(did) + 1] != next_id:
                raise ValueError('只能与下一题合并。')
            data, other = json.loads(left['data']), json.loads(right['data'])
            before = [dict(data), dict(other)]
            data['stem'] += '\n\n' + other['stem']
            if other['options']:
                data['stem'] += '\n' + '\n'.join(f'{letter}. {text}' for letter, text in zip('ABCD', other['options']))
            for field in ('answer', 'solution'):
                if other[field]:
                    data[field] += ('\n\n' if data[field] else '') + other[field]
            data['fragments'] += [f for f in other['fragments'] if f not in data['fragments']]
            data['raw_ocr'] += '\n\n' + other['raw_ocr']
            data.update(status='pending', math_verified=False)
            data['issues'] = list(dict.fromkeys(data['issues'] + other['issues'] + ['手动合并：请核对题干、选项及答案对应关系，另一草稿保留于识别记录。']))
            other['status'] = 'merged'
            other['merged_into'] = did
            for key, item in ((did, data), (next_id, other)):
                db.execute('UPDATE drafts SET revision=revision+1,data=? WHERE id=?', (dumps(item), key))
            self.event(db, 'merge_draft', {'ids': [did, next_id], 'before': before})
        return self.draft(did)

    def set_review(self, did, revision, status):
        if status not in ('pending', 'confirmed', 'skipped'):
            raise ValueError('状态错误。')
        with self.connect() as db:
            row = db.execute('SELECT * FROM drafts WHERE id=?', (did,)).fetchone()
            if not row:
                raise KeyError('题目不存在。')
            if row['revision'] != revision:
                raise Conflict('题目已修改，请重新核对当前版本。')
            data = json.loads(row['data'])
            if status == 'confirmed':
                if not data['stem'].strip():
                    raise ValueError('请补充题干。')
                if data['type'] == '选择题' and (len(data['options']) != 4 or any(not v.strip() for v in data['options'])):
                    raise ValueError('请补齐四个选项，或暂存待人工检查。')
                if not data['answer'].strip():
                    raise ValueError('未匹配到答案，请补充后确认，或暂存待人工检查。')
            data['status'] = status
            db.execute('UPDATE drafts SET revision=revision+1,data=? WHERE id=?', (dumps(data), did))
            self.event(db, 'review', {'id': did, 'status': status, 'math_verified': False})
        return self.draft(did)

    def commit(self, bid):
        batch = self.batch(bid)
        if batch['status'] not in ('completed',):
            raise ValueError('请等待识别完成再确认入库。')
        result = {'added': [], 'duplicates': [], 'pending': 0, 'skipped': 0}
        with self.connect() as db:
            for row in db.execute('SELECT id,data FROM drafts WHERE batch_id=?', (bid,)).fetchall():
                draft = json.loads(row['data'])
                if draft['status'] == 'merged':
                    continue
                if draft['status'] != 'confirmed':
                    result['skipped' if draft['status'] == 'skipped' else 'pending'] += 1
                    continue
                fingerprint = body_hash(draft['stem'], draft['options'])
                old = db.execute('SELECT id FROM bank WHERE id=? OR body_hash=? LIMIT 1', (draft['question_id'], fingerprint)).fetchone()
                if old:
                    result['duplicates'].append(old['id'])
                    continue
                question = dict(draft, source_name=batch['source']['name'], batch_id=bid,
                                transcription_reviewed=True, math_verified=False)
                db.execute('INSERT INTO bank VALUES(?,?,?,?)', (draft['question_id'], fingerprint, dumps(question), now()))
                result['added'].append(draft['question_id'])
            self.event(db, 'commit', dict(batch=bid, **result))
        return result

    def bank(self):
        with self.connect() as db:
            return [dict(json.loads(r['data']), id=r['id']) for r in db.execute('SELECT * FROM bank ORDER BY created DESC')]
