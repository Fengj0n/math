import hashlib
import json
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from . import VERSION
from .config import APP_DIR, CHAPTERS, DATA, configure_environment, subject_for
from .ocr import model_status
from .processor import Processor
from .splitter import parse_pages
from .store import Conflict, Store, dumps

MAX_UPLOAD = 256 * 1024 * 1024
HEX_ID = re.compile(r'^[0-9a-f]{32,64}$')


def create_app(data_root=None, recogniser=None):
    configure_environment()
    store = Store(data_root or DATA)
    processor = Processor(store, recogniser)

    @asynccontextmanager
    async def lifespan(app):
        yield
        processor.close()

    app = FastAPI(title='本地PDF题目导入', lifespan=lifespan)
    app.state.store, app.state.processor = store, processor

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        host = request.headers.get('host', '').split(':')[0]
        if host not in ('127.0.0.1', 'localhost', 'testserver'):
            return JSONResponse({'detail': '仅允许本机访问。'}, 403)
        origin = request.headers.get('origin')
        if origin and origin != f'http://{request.headers.get("host")}':
            return JSONResponse({'detail': '不接受外部网页提交。'}, 403)
        try:
            if int(request.headers.get('content-length', '0')) > MAX_UPLOAD + 1024 * 1024:
                return JSONResponse({'detail': '单个PDF不能超过256MB。'}, 413)
        except ValueError:
            return JSONResponse({'detail': '请求长度错误。'}, 400)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; object-src 'none'"
        return response

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse({'detail': str(exc)}, 409)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'detail': str(exc)}, 400)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail': str(exc).strip("'")}, 404)

    @app.get('/api/health')
    def health():
        return {'app': 'math2-local-pdf-import', 'version': VERSION, 'recogniser': model_status(),
                'bank_count': len(store.bank()), 'data_dir': str(store.root), 'chapters': CHAPTERS,
                'can_shutdown': callable(getattr(app.state, 'shutdown', None)),
                'notice': '只写入独立试用库；识别结果需要核对，未自动确认数学正确性。'}

    @app.post('/api/shutdown')
    def shutdown():
        callback = getattr(app.state, 'shutdown', None)
        if not callable(callback):
            raise HTTPException(503, '当前启动方式不支持从页面关闭。')
        return JSONResponse({'message': '本地服务正在关闭，保存的记录会保留。'}, background=BackgroundTask(callback))

    @app.post('/api/sources')
    async def upload(file: UploadFile = File(...)):
        import pymupdf
        if not (file.filename or '').lower().endswith('.pdf'):
            raise ValueError('请选择PDF文件。')
        temp = store.root / 'sources' / (uuid.uuid4().hex + '.upload')
        total, digest = 0, hashlib.sha256()
        try:
            with temp.open('wb') as out:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_UPLOAD:
                        raise HTTPException(413, '单个PDF不能超过256MB。')
                    digest.update(chunk)
                    out.write(chunk)
            if total == 0:
                raise ValueError('PDF文件为空。')
            with temp.open('rb') as check:
                if b'%PDF-' not in check.read(1024):
                    raise ValueError('文件不是有效PDF。')
            try:
                with pymupdf.open(temp, filetype='pdf') as doc:
                    if doc.needs_pass:
                        raise ValueError('此PDF有密码保护，请先提供可直接打开的副本。')
                    count = len(doc)
                    if not 1 <= count <= 1500:
                        raise ValueError('仅支持1至1500页的PDF。')
            except (pymupdf.FileDataError, RuntimeError) as exc:
                raise ValueError('无法打开PDF，文件可能损坏。') from exc
            sid = digest.hexdigest()
            destination = store.root / 'sources' / f'{sid}.pdf'
            if not destination.exists():
                temp.replace(destination)
            store.add_source(sid, Path(file.filename.replace('\\', '/')).name[:180], count)
            return store.source(sid)
        finally:
            await file.close()
            if temp.exists():
                temp.unlink()

    @app.get('/api/sources/{sid}/page/{pnum}')
    def source_page(sid: str, pnum: int, x0: float = 0, y0: float = 0, x1: float = 1, y1: float = 1):
        import pymupdf
        source = store.source(sid)
        if not HEX_ID.fullmatch(sid) or not 1 <= pnum <= source['pages'] or not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError('原页或区域无效。')
        with pymupdf.open(store.root / 'sources' / f'{sid}.pdf') as doc:
            page = doc[pnum - 1]
            rect = page.rect
            clip = pymupdf.Rect(x0 * rect.width, y0 * rect.height, x1 * rect.width, y1 * rect.height)
            zoom = min(2.2, 1800 / max(clip.width, clip.height))
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
            return Response(pix.tobytes('png'), media_type='image/png')

    @app.get('/api/batches')
    def batches():
        return store.batches()

    @app.post('/api/batches')
    def start(body: dict):
        if recogniser is None and not model_status()['ready']:
            raise HTTPException(503, model_status()['message'])
        source = store.source(str(body.get('source_id', '')))
        pages = parse_pages(body.get('pages', ''), source['pages'])
        chapter = str(body.get('chapter') or '未归类')
        if chapter != '未归类' and chapter not in sum(CHAPTERS.values(), []):
            raise ValueError('章节无效。')
        batch = store.create_batch(source['id'], pages, chapter)
        if batch['status'] != 'completed':
            processor.submit(batch['id'])
        return store.batch(batch['id'])

    @app.get('/api/batches/{bid}')
    def batch(bid: str):
        result = store.batch(bid)
        path = store.root / 'pages' / f'{bid}-unassigned.json'
        result['unassigned'] = json.loads(path.read_text('utf-8')) if path.exists() else []
        return result

    @app.post('/api/batches/{bid}/resume')
    def resume(bid: str):
        batch = store.batch(bid)
        if batch['status'] != 'completed':
            processor.submit(bid)
        return store.batch(bid)

    @app.post('/api/batches/{bid}/cancel')
    def cancel(bid: str):
        store.batch(bid)
        processor.cancel(bid)
        return store.batch(bid)

    @app.put('/api/drafts/{did}')
    def edit(did: str, body: dict):
        return store.edit_draft(did, body.get('revision'), body.get('fields', {}))

    @app.post('/api/drafts/{did}/review')
    def review(did: str, body: dict):
        return store.set_review(did, body.get('revision'), body.get('status'))

    @app.post('/api/drafts/{did}/split')
    def split(did: str, body: dict):
        return store.split_draft(did, body.get('revision'), body.get('offset'))

    @app.post('/api/drafts/{did}/merge')
    def merge(did: str, body: dict):
        return store.merge_draft(did, body.get('revision'), body.get('next_id'), body.get('next_revision'))

    @app.post('/api/batches/{bid}/commit')
    def commit(bid: str, body: dict):
        if body.get('accept_review') is not True:
            raise ValueError('请确认已核对本批次准备入库的题目。')
        return store.commit(bid)

    @app.get('/api/bank')
    def bank():
        return store.bank()

    @app.get('/api/bank/export')
    def export():
        rows = []
        for q in store.bank():
            rows.append({'ID': q['id'], '来源': 'PDF导入', '原题编号': q['number'], '科目': subject_for(q['chapter']),
                         '一级知识点': q['chapter'], '二级知识点': q['point'], '三级知识点': q['model'],
                         '题型': q['type'], '题干': q['stem'], '选项': q['options'], '标准答案': q['answer'], '解析': q['solution'],
                         '正文可程序化使用': False, '数学疑点状态': '待人工检查', '录入核对状态': '已人工核对录入',
                         '原始文件来源': q['source_name'], '题干PDF页': [f['page'] for f in q['fragments']],
                         '_pdf_import': {'source_sha256': q['source_id'], 'fragments': q['fragments'], 'math_verified': False}})
        return Response(dumps({'format': 'math2-local-pdf-intake-v1', 'items': rows}), media_type='application/json',
                        headers={'Content-Disposition': 'attachment; filename="pdf-import-questions.json"'})

    @app.get('/vendor/{name}')
    def vendor(name: str):
        source = (APP_DIR / 'design' / 'question-bank.html').read_text('utf-8')
        if name == 'math.css':
            return Response(re.findall(r'<style>([\s\S]*?)</style>', source)[0], media_type='text/css')
        if name == 'katex.js':
            return Response(re.findall(r'<script>([\s\S]*?)</script>', source)[0], media_type='application/javascript')
        raise HTTPException(404)

    @app.get('/bank', response_class=HTMLResponse)
    def bank_view():
        source = (APP_DIR / 'design' / 'question-bank.html').read_text('utf-8')
        pattern = r'const BANK_DATA = ([\s\S]*?);\s*const root='
        match = re.search(pattern, source)
        original = json.loads(match[1])
        for q in store.bank():
            original.append({'id': q['id'], 'source': 'PDF导入', 'source_title': q['source_name'], 'subject': subject_for(q['chapter']),
                             'chapter': q['chapter'], 'point': q['point'], 'model': q['model'], 'type': q['type'], 'original_number': q['number'] or '?',
                             'stem': q['stem'], 'options': q['options'], 'answer': q['answer'], 'solution': q['solution'],
                             'provenance': q['source_name'] + '，PDF第' + ','.join(str(f['page']) for f in q['fragments']) + '页；已核对录入，数学结论尚待复核。',
                             'parts': [], 'difficulty': None, 'calculation': None, 'year': None, 'original_points': None})
        source = source[:match.start(1)] + dumps(original).replace('</', '<\\/') + source[match.end(1):]
        source = source.replace("function label(q){", "function label(q){if(q.source==='PDF导入')return q.source_title+' · 第'+q.original_number+'题';")
        source = source.replace("['项目原创示例','原创示例']", "['项目原创示例','原创示例'],['PDF导入','PDF导入']")
        source = source.replace('const pageSize=6;', "chapterGroups.push({name:'待整理',chapters:['未归类']});const pageSize=6;")
        source = source.replace("case 'open':imp.open=true;", "case 'open':location.href='/';return;imp.open=true;")
        source = source.replace(' · 抽样预览', ' · 独立试用')
        source = source.replace('设计预览 · 本页选择与笔记仅用于预览', '独立试用库 · 78道设计预览题与已核对导入题；录入核对不代表数学正确性复核')
        # The standalone trial has its own UI state, separate from in-chat previews.
        adapter = """<script>let saved=null;try{saved=JSON.parse(localStorage.getItem('math2-local-pdf-bank-v1')||'null')}catch{}window.openai={widgetState:saved,setWidgetState:async s=>{localStorage.setItem('math2-local-pdf-bank-v1',JSON.stringify(s))}};</script>"""
        return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>题库 · 本地导入试用</title><body style="margin:20px"><script src="/static/icons.js"></script>' + adapter + source + '</body></html>'

    app.mount('/static', StaticFiles(directory=Path(__file__).parent / 'static'), name='static')

    @app.get('/')
    def index():
        return FileResponse(Path(__file__).parent / 'static' / 'index.html')

    return app
