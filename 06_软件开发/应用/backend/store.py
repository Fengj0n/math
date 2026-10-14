"""Versioned SQLite repository; transactions are the only write boundary."""
import contextlib, datetime, json, sqlite3, uuid, threading

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def uid(prefix):return prefix+'-'+uuid.uuid4().hex[:16]
def dumps(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'))

class Store:
    def __init__(self,path):
        self.path=path;self.lock=threading.RLock();path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            INSERT OR IGNORE INTO meta VALUES('schema','1');
            CREATE TABLE IF NOT EXISTS imports(hash TEXT PRIMARY KEY,name TEXT NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS questions(id TEXT PRIMARY KEY,current_rev TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS revisions(rev TEXT PRIMARY KEY,id TEXT NOT NULL,hash TEXT NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS revision_id ON revisions(id);
            CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY,favorite INTEGER NOT NULL DEFAULT 0,note TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS papers(id TEXT PRIMARY KEY,created TEXT NOT NULL,archived INTEGER NOT NULL DEFAULT 0,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY,paper_id TEXT NOT NULL,version INTEGER NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,state TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,created TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL);
            ''')

    @contextlib.contextmanager
    def connect(self):
        with self.lock:
            c=sqlite3.connect(self.path,timeout=10);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
            try:yield c;c.commit()
            except BaseException:c.rollback();raise
            finally:c.close()

    def event(self,c,kind,payload):c.execute('INSERT INTO events VALUES(?,?,?,?)',(uid('E'),now(),kind,dumps(payload)))
    def questions(self):
        with self.connect() as c:
            rows=c.execute('SELECT r.payload,n.favorite,n.note,n.version FROM questions q JOIN revisions r ON r.rev=q.current_rev LEFT JOIN notes n ON n.id=q.id').fetchall()
        return [dict(json.loads(r['payload']),favorite=bool(r['favorite']),personal_note=r['note'] or '',note_version=r['version'] or 0) for r in rows]
    def question(self,qid):
        with self.connect() as c:r=c.execute('SELECT r.payload FROM questions q JOIN revisions r ON r.rev=q.current_rev WHERE q.id=?',(qid,)).fetchone()
        if not r:raise KeyError('题目不存在')
        return json.loads(r[0])
    def paper(self,pid):
        with self.connect() as c:r=c.execute('SELECT payload FROM papers WHERE id=?',(pid,)).fetchone()
        if not r:raise KeyError('试卷不存在')
        return json.loads(r[0])
    def attempt(self,aid):
        with self.connect() as c:r=c.execute('SELECT payload FROM attempts WHERE id=?',(aid,)).fetchone()
        if not r:raise KeyError('练习不存在')
        return json.loads(r[0])
