"""Loopback application API. Immutable paper snapshots and explicit grading boundaries."""
import copy, hashlib, json, logging, os, pathlib, re, sqlite3, sys, threading, zipfile,contextlib
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .domain import normalize, parse_source, digest, grade, slot, structure, design, assemble
from .store import Store, now, uid, dumps
from .presentation import prepare, VERSION as LAYOUT_VERSION
from .question_images import ImageCatalogue

VERSION='1.2.0'
APP_DIR=pathlib.Path(getattr(sys,'_MEIPASS',pathlib.Path(__file__).resolve().parents[1]))
ROOT=pathlib.Path(os.environ.get('MATH2_HOME',pathlib.Path(sys.executable).parent if getattr(sys,'frozen',False) else APP_DIR.parent)).resolve()
PROJECT=ROOT.parent if ROOT.name=='06_软件开发' else None
DATA=ROOT/'用户数据';EXPORT=ROOT/'导出';BACKUP=ROOT/'备份'
for p in (DATA,EXPORT,BACKUP):p.mkdir(parents=True,exist_ok=True)
store=Store(DATA/'math2.sqlite3')
image_catalogue=ImageCatalogue(APP_DIR)
rules=json.loads((APP_DIR/'assets'/'rules.json').read_text(encoding='utf-8'))
app=FastAPI(title='考研数学二智能命题与审卷系统',version=VERSION,docs_url=None,redoc_url=None)
previews={};preview_lock=threading.Lock()
logging.basicConfig(filename=DATA/'服务日志.log',encoding='utf-8',level=logging.INFO)

def fail(message,status=400):raise HTTPException(status,detail=message)
def require(condition,message,status=400):
    if not condition:fail(message,status)
def bounded(value,minimum,maximum,name):
    require(isinstance(value,int) and not isinstance(value,bool) and minimum<=value<=maximum,f'{name}应为{minimum}—{maximum}的整数')
    return value
def safe_name(name):
    name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',str(name)).strip(' .')[:90] or '试卷'
    if name.upper().split('.')[0] in ('CON','PRN','AUX','NUL') or re.fullmatch(r'(COM|LPT)\d',name.upper()):name='_'+name
    return name
def unique(directory,name,ext):
    return directory/(safe_name(name)+'_'+uid('')[-8:]+ext)
def public_paper(p):
    """Whitelist, rather than deleting known answer fields from raw imported payload."""
    out={k:p.get(k) for k in ('id','title','mode','minutes','created','parent_id','version')}
    out['items']=[{'number':it['number'],'points':it['points'],'locked':it.get('locked',False),
                   'question':{k:it['question'].get(k) for k in ('id','revision','stem','options','parts','type')}} for it in p['items']]
    return out

def display_paper(p):
    """Render a copy under current rules; immutable stored snapshots stay intact."""
    p=copy.deepcopy(p)
    for it in p['items']:it['question']=image_catalogue.decorate(prepare(it['question']))
    p['display_layout_version']=LAYOUT_VERSION
    p['checks']=structure(p['items'],p['mode'])
    return p

@app.middleware('http')
async def loopback(request:Request,call_next):
    host=request.headers.get('host','').split(':')[0]
    if host not in ('127.0.0.1','localhost','testserver'):return JSONResponse({'detail':'仅允许本机访问'},403)
    origin=request.headers.get('origin')
    if origin and origin not in (f'http://{request.headers.get("host")}', 'http://127.0.0.1:5173'):return JSONResponse({'detail':'拒绝跨站请求'},403)
    if int(request.headers.get('content-length','0'))>50*1024*1024:return JSONResponse({'detail':'输入超过50MB'},413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='public, max-age=31536000, immutable' if request.url.path.startswith('/api/question-images/') else 'no-store' if request.url.path.startswith('/api') else 'public, max-age=3600'
    return response

@app.exception_handler(KeyError)
async def missing(_request,exc):return JSONResponse({'detail':str(exc)},404)
@app.exception_handler(ValueError)
async def invalid(_request,exc):return JSONResponse({'detail':str(exc)},400)
@app.exception_handler(sqlite3.OperationalError)
async def db_error(_request,exc):
    logging.error('数据库操作失败: %s',type(exc).__name__)
    return JSONResponse({'detail':'数据库繁忙或磁盘不可写，请检查数据目录后重试'},503)

def import_questions(rows,name,hash_value):
    with store.connect() as c:
        if c.execute('SELECT 1 FROM imports WHERE hash=?',(hash_value,)).fetchone():return {'duplicate':True,'added':0,'updated':0}
        added=updated=unchanged=0;conflicts=[]
        for q in rows:
            old=c.execute('SELECT r.payload FROM questions t JOIN revisions r ON r.rev=t.current_rev WHERE t.id=?',(q['id'],)).fetchone()
            if old and json.loads(old[0])['payload_hash']==q['payload_hash']:unchanged+=1;continue
            if old:
                updated+=1
                edited=c.execute('SELECT id FROM questions WHERE id LIKE ?',('EDIT-'+q['id']+'-%',)).fetchall()
                if edited:conflicts.append({'id':q['id'],'retained_edit_ids':[e[0] for e in edited]})
            else:added+=1
            q=copy.deepcopy(q);q['revision']=uid('R');q['import_hash']=hash_value
            c.execute('INSERT INTO revisions VALUES(?,?,?,?,?)',(q['revision'],q['id'],q['payload_hash'],now(),dumps(q)))
            c.execute('INSERT INTO questions VALUES(?,?) ON CONFLICT(id) DO UPDATE SET current_rev=excluded.current_rev',(q['id'],q['revision']))
        result={'added':added,'updated':updated,'unchanged':unchanged,'retained_edits':conflicts,'total':len(rows)}
        c.execute('INSERT INTO imports VALUES(?,?,?,?)',(hash_value,name,now(),dumps(result)));store.event(c,'import',result)
    return result

@app.get('/api/health')
def health():return {'app':'math2-studio','version':VERSION,'schema':1}

@app.get('/api/dashboard')
def dashboard():
    qs=store.questions()
    with store.connect() as c:
        papers=[json.loads(r[0]) for r in c.execute('SELECT payload FROM papers WHERE archived=0 ORDER BY created DESC LIMIT 5')]
        attempts=[json.loads(r[0]) for r in c.execute('SELECT payload FROM attempts ORDER BY created DESC')]
    submitted=[a for a in attempts if a['status']=='submitted']
    confirmed=[g for a in submitted for g in a.get('grades',{}).values() if g['origin']=='自动' and g['state'] in ('正确','错误')]
    return {'questions':len(qs),'body_ready':sum(q['source_body_ready'] for q in qs),'eligible':sum(q['eligible'] for q in qs),
            'standard_ready':sum(q['eligible'] and q['compatibility'] for q in qs),'auto_grade':sum(q['auto_grade_ready'] and q['eligible'] for q in qs),
            'pending':sum(not q['eligible'] for q in qs),'favorites':sum(q['favorite'] for q in qs),'papers':[{k:p[k] for k in ('id','title','created','mode','checks')} for p in papers],
            'attempts':[{k:a[k] for k in ('id','paper_id','status','elapsed','created')} for a in attempts[:8]],
            'confirmed_answered':len(confirmed),'confirmed_correct':sum(g['state']=='正确' for g in confirmed),
            'pending_grades':sum(g['score'] is None for a in submitted for g in a.get('grades',{}).values()),'version':VERSION}

@app.get('/api/questions')
def questions(search:str='',source:str='',subject:str='',chapter:str='',type:str='',year:str='',difficulty:str='',ready:str='',favorite:bool=False,page:int=1,size:int=20):
    bounded(page,1,10000,'页码');bounded(size,1,100,'每页数量');require(len(search)<=200,'搜索词过长')
    rows=[image_catalogue.decorate(q) for q in store.questions()];filters={'source':source,'subject':subject,'chapter':chapter,'type':type,'year':year,'difficulty':difficulty}
    def ready_match(q):
        if not ready:return True
        if ready=='eligible':return q['eligible']
        if ready=='viewable':return q['eligible'] or q['image_ready']
        if ready=='images':return q['image_ready']
        return not q['eligible']
    rows=[q for q in rows if all(not v or str(q.get(k))==v for k,v in filters.items()) and (not favorite or q['favorite']) and ready_match(q) and (not search or search.lower() in (' '.join(str(q.get(k,'')) for k in ('id','stem','chapter','point','model','core','original_number'))).lower())]
    rows.sort(key=lambda q:(not q['eligible'],q['id']))
    keys=('id','revision','source','year','original_number','subject','chapter','point','model','type','original_points','difficulty','calculation','stem','eligible','auto_grade_ready','compatibility','review','favorite','personal_note','note_version','image_ready','image_mode','image_status','body_display_mode','question_images','reference_images','category')
    return {'total':len(rows),'page':page,'items':[{k:q.get(k) for k in keys} for q in rows[(page-1)*size:page*size]]}

@app.get('/api/filters')
def filters():
    qs=store.questions()
    return {k:sorted({str(q[k]) for q in qs if q.get(k) is not None and q.get(k)!=''}) for k in ('source','subject','chapter','type','year','difficulty')}

@app.get('/api/questions/{qid}')
def question(qid:str):
    q=store.question(qid)
    with store.connect() as c:
        note=c.execute('SELECT * FROM notes WHERE id=?',(qid,)).fetchone()
        revs=c.execute('SELECT rev,created,hash FROM revisions WHERE id=? ORDER BY created DESC',(qid,)).fetchall()
    q['personal_note']=note['note'] if note else '';q['favorite']=bool(note['favorite']) if note else False;q['note_version']=note['version'] if note else 0
    q['history']=[dict(r) for r in revs];return image_catalogue.decorate(q)

@app.get('/api/question-images/{name}')
def question_image(name:str):
    return FileResponse(image_catalogue.file(name),media_type='image/webp')

@app.put('/api/questions/{qid}/note')
def note(qid:str,body:dict):
    store.question(qid);require(len(str(body.get('note','')))<=5000,'笔记超过5000字')
    with store.connect() as c:
        old=c.execute('SELECT version FROM notes WHERE id=?',(qid,)).fetchone();v=old[0] if old else 0
        require(body.get('version')==v,'笔记已在另一页面修改，请刷新后重试',409)
        c.execute('INSERT INTO notes VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET favorite=excluded.favorite,note=excluded.note,version=excluded.version',(qid,bool(body.get('favorite')),body.get('note',''),v+1))
    return {'version':v+1}

@app.post('/api/questions')
def create_question(body:dict):
    raw=body.get('raw',{});require(isinstance(raw,dict),'题目数据格式错误')
    raw['ID']=uid('PERSONAL');raw['来源']='个人录入';raw['正文可程序化使用']=False
    q=normalize(raw);return dict(import_questions([q],'个人录入',digest(raw)),id=q['id'])

@app.post('/api/questions/{qid}/edit-copy')
def edit_copy(qid:str,body:dict):
    old=store.question(qid);require(body.get('revision')==old['revision'],'来源修订已变化，请刷新',409)
    fields=body.get('fields',{});require(isinstance(fields,dict),'编辑数据格式错误')
    allowed={'题干','标准答案','解析','选项','一级知识点','二级知识点','三级知识点','难度','计算量'}
    require(set(fields)<=allowed,'包含不允许编辑的字段')
    raw={'ID':uid('EDIT-'+qid),'来源':'个人编辑副本','origin_id':old['origin_id'],'年份':old['year'],'原题编号':old['original_number'],
         '科目':old['subject'],'一级知识点':old['chapter'],'二级知识点':old['point'],'三级知识点':old['model'],'知识点代码':old['code'],
         '题型':old['type'],'题干':old['stem'],'选项':old['options'],'标准答案':old['answer'],'解析':old['solution'],
         '分值':old['original_points'],'难度':old['difficulty'],'计算量':old['calculation'],'正文可程序化使用':False,
         '原始文件来源':old['provenance'],'父修订':old['revision']}
    raw.update(fields);q=normalize(raw)
    return dict(import_questions([q],'编辑副本',digest(raw)),id=q['id'],review='待人工检查')

@app.get('/api/questions/{qid}/asset/{role}/{index}')
def asset(qid:str,role:str,index:int):
    require(role in ('question','answer_reference'),'资源类型不允许');q=store.question(qid)
    entry=image_catalogue.entry(q)
    if entry:
        images=entry['reference_images' if role=='question' else 'answer_images']
        require(0<=index<len(images),'资源不存在',404)
        return FileResponse(image_catalogue.file(images[index]['url'].rsplit('/',1)[-1]),media_type='image/webp')
    require(PROJECT is not None,'此运行包没有上游原页；请在原项目版本查看')
    assets=q['source_assets'].get(role,[]);require(0<=index<len(assets),'资源不存在',404)
    ref=assets[index];path=(PROJECT/ref['image_path']).resolve()
    require(path.is_relative_to(PROJECT) and path.suffix.lower()=='.png','资源路径越界')
    require(path.exists(),'原页资源缺失',404)
    if ref.get('image_sha256'):require(hashlib.sha256(path.read_bytes()).hexdigest()==ref['image_sha256'],'原页指纹已变化，待人工检查')
    return FileResponse(path)

@app.get('/api/data/info')
def data_info():
    with store.connect() as c:imports=[dict(r) for r in c.execute('SELECT hash,name,created,payload FROM imports ORDER BY created DESC')]
    return {'version':VERSION,'data_dir':str(DATA),'exports_dir':str(EXPORT),'backup_dir':str(BACKUP),'imports':imports,'rules':rules,'project_available':PROJECT is not None}

@app.post('/api/import/preview')
def preview(body:dict):
    if body.get('builtin'):
        require(PROJECT is not None,'当前便携包不包含第三方题库；请选择JSON文件导入')
        mapping={'bank':'02_题库/数学二题库.json','selected':'02_题库/命题精选素材.json'}
        require(body['builtin'] in mapping,'未知内置来源');path=PROJECT/mapping[body['builtin']];name=path.name;data=json.loads(path.read_text(encoding='utf-8-sig'))
    else:data=body.get('data');name=safe_name(body.get('name','导入数据'))
    require(isinstance(data,(dict,list)),'请选择有效JSON资料')
    rows=parse_source(data);h=digest(data);token=uid('PREVIEW')
    with preview_lock:
        if len(previews)>10:previews.pop(next(iter(previews)))
        previews[token]=(rows,name,h)
    with store.connect() as c:duplicate=bool(c.execute('SELECT 1 FROM imports WHERE hash=?',(h,)).fetchone())
    return {'token':token,'name':name,'hash':h,'count':len(rows),'eligible':sum(q['eligible'] for q in rows),'pending':sum(not q['eligible'] for q in rows),'duplicate':duplicate,'notice':'已保留全部原始字段；提交前尚未写入题库'}

@app.post('/api/import/commit')
def commit(body:dict):
    with preview_lock:item=previews.pop(body.get('token',''),None)
    require(item is not None,'导入预览已失效，请重新预览');return import_questions(*item)

def paper_record(title,mode,items,seed=None,parent=None):
    return {'id':uid('P'),'title':str(title or '数学二练习卷')[:120],'version':1,'parent_id':parent,'created':now(),'mode':mode,
            'minutes':180 if mode=='standard' else None,'items':copy.deepcopy(items),'seed':seed,
            'material_hash':digest([(q['id'],q['revision']) for q in sorted(store.questions(),key=lambda x:x['id'])]),
            'rule_version':rules['version'],'checks':structure(items,mode),'design':design(items,rules) if mode=='standard' else {'pending':['章节练习不以标准卷配额评价'],'warnings':[]}}

def save_paper(p):
    with store.connect() as c:c.execute('INSERT INTO papers VALUES(?,?,0,?)',(p['id'],p['created'],dumps(p)));store.event(c,'paper_saved',{'id':p['id'],'count':len(p['items'])})
    return p

@app.post('/api/assemble')
def assemble_api(body:dict):
    budget=bounded(body.get('budget',1000),1,10000,'搜索节点预算');locked={int(k):v for k,v in body.get('locked',{}).items()};require(all(1<=k<=22 for k in locked),'锁定题位不合法')
    mode=body.get('source_mode','original');require(mode in ('original','training'),'素材模式不合法')
    pool=store.questions()
    if mode=='original':pool=[q for q in pool if q['source'] in ('项目原创示例','审核后原创题','AI自动审核原创题')]
    result=assemble(pool,str(body.get('seed','2027')),rules,locked,budget)
    if result.get('items'):
        result['paper']=paper_record(body.get('title'), 'standard',result.pop('items'),body.get('seed'));result['paper']['source_mode']=mode
    return result

@app.post('/api/papers')
def papers_save(body:dict):
    if body.get('draft'):
        draft=body['draft'];require(draft.get('mode')=='standard','草稿模式不支持')
        items=draft.get('items',[]);require(len(items)<=22,'题数超过模板')
        # Re-fetch by revision; never trust answer data sent by a browser.
        verified=[]
        for n,it in enumerate(items,1):
            q=store.question(it['question']['id']);require(q['revision']==it['question']['revision'],'题库修订发生变化，请重新选题',409)
            verified.append({'number':n,'points':it.get('points'),'locked':bool(it.get('locked')),'question':q})
        p=paper_record(body.get('title',draft.get('title')), 'standard',verified,draft.get('seed'),draft.get('parent_id'))
        require(p['checks']['passed'],'；'.join(p['checks']['errors']))
        source_mode=draft.get('source_mode','training');require(source_mode in ('original','training'),'素材模式不合法')
        if source_mode=='original':require(all(it['question']['source'] in ('项目原创示例','审核后原创题','AI自动审核原创题') for it in verified),'原创卷包含非原创来源')
        p['source_mode']=source_mode;return save_paper(p)
    ids=body.get('ids',[]);require(isinstance(ids,list) and 1<=len(ids)<=100,'章节练习应选1—100题')
    qs=[store.question(qid) for qid in ids];require(all(q['eligible'] for q in qs),'包含待人工检查或缺失正文题')
    items=[{'number':i,'question':q,'points':q['original_points'],'locked':False} for i,q in enumerate(qs,1)]
    p=paper_record(body.get('title'),'chapter',items);require(p['checks']['passed'],'；'.join(p['checks']['errors']))
    return save_paper(p)

@app.get('/api/papers')
def papers(search:str='',archived:bool=False):
    with store.connect() as c:rows=[json.loads(r[0]) for r in c.execute('SELECT payload FROM papers WHERE archived=? ORDER BY created DESC',(int(archived),))]
    return [{k:p.get(k) for k in ('id','title','mode','created','checks','parent_id')} for p in rows if search.lower() in p['title'].lower()]

@app.get('/api/papers/{pid}')
def get_paper(pid:str,exam:bool=False):
    p=display_paper(store.paper(pid));return public_paper(p) if exam else p

@app.post('/api/papers/{pid}/archive')
def archive(pid:str,body:dict):
    store.paper(pid)
    with store.connect() as c:c.execute('UPDATE papers SET archived=? WHERE id=?',(bool(body.get('archived',True)),pid))
    return {'saved':True}

@app.get('/api/papers/{pid}/exchange')
def exchange(pid:str):
    paper=store.paper(pid);require(paper['checks']['passed'],'结构有误的草稿不能作为合规卷交换')
    clean=copy.deepcopy(paper)
    for it in clean['items']:
        q=it['question'];q.pop('raw_payload',None);q.pop('source_assets',None);q.pop('personal_note',None);q.pop('favorite',None);q.pop('note_version',None)
    return {'schema':'math2-paper-1','paper':clean,'sha256':digest(clean),'notice':'包含答案，适合本地交换；不构成防作弊加密'}

@app.post('/api/exchange/preview')
def exchange_preview(body:dict):
    require(body.get('schema')=='math2-paper-1','交换包版本不兼容');p=body.get('paper',{});require(digest(p)==body.get('sha256'),'交换包指纹不匹配')
    require(p.get('mode') in ('standard','chapter') and isinstance(p.get('items'),list) and 1<=len(p['items'])<=100,'交换包结构错误')
    for it in p['items']:
        q=it.get('question',{});require(all(k in q for k in ('id','revision','stem','answer','solution','type','subject','eligible','origin_id')),'交换题目字段缺失')
        require(len(str(q['stem']))<30000 and len(str(q['solution']))<100000,'交换题目过大')
        require(not q.get('source_assets'),'本版本只交换无附件正文，不支持整页资料混入')
    check=structure(p['items'],p['mode']);require(check['passed'],'交换包违反题目或分值约束：'+'；'.join(check['errors']))
    return {'title':p['title'],'count':len(p['items']),'mode':p['mode'],'hash':body['sha256'],'checks':check}

@app.post('/api/exchange/import')
def exchange_import(body:dict):
    exchange_preview(body);p=copy.deepcopy(body['paper']);h=body['sha256']
    with store.connect() as c:
        exists=c.execute('SELECT value FROM meta WHERE key=?',('exchange:'+h,)).fetchone()
        if exists:return {'duplicate':True,'id':exists[0]}
        p['exchange_origin_id']=p['id'];p['id']=uid('P');p['created']=now();p['checks']=structure(p['items'],p['mode'])
        c.execute('INSERT INTO papers VALUES(?,?,0,?)',(p['id'],p['created'],dumps(p)));c.execute('INSERT INTO meta VALUES(?,?)',('exchange:'+h,p['id']))
    return {'id':p['id'],'duplicate':False}

@app.post('/api/attempts')
def start_attempt(body:dict):
    p=display_paper(store.paper(body.get('paper_id')));require(p['checks']['passed'],'试卷存在硬约束或排版错误，不能开始练习')
    a={'id':uid('A'),'paper_id':p['id'],'created':now(),'status':'active','version':0,'elapsed':0,'responses':{},'grades':{},'score_history':[]}
    with store.connect() as c:c.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?)',(a['id'],p['id'],0,'active',a['created'],dumps(a)))
    return a

@app.get('/api/attempts')
def attempts():
    with store.connect() as c:rows=[json.loads(r[0]) for r in c.execute('SELECT payload FROM attempts ORDER BY created DESC')]
    return [{k:a[k] for k in ('id','paper_id','status','elapsed','created','version')} for a in rows]

@app.get('/api/attempts/{aid}')
def get_attempt(aid:str):
    a=store.attempt(aid);p=display_paper(store.paper(a['paper_id']));out=copy.deepcopy(a)
    out['paper']=p if a['status']=='submitted' else public_paper(p)
    if a['status']=='submitted':out['summary']=score_summary(a)
    return out

def score_summary(a):
    gs=list(a['grades'].values())
    return {'automatic_score':sum(g['score'] or 0 for g in gs if g['origin']=='自动'),
            'self_score':sum(g['score'] or 0 for g in gs if g['origin']=='自评'),'manual_score':sum(g['score'] or 0 for g in gs if g['origin']=='人工'),
            'pending':sum(g['score'] is None for g in gs),'confirmed_correct':sum(g['state']=='正确' and g['origin']=='自动' for g in gs),
            'confirmed_answered':sum(g['state'] in ('正确','错误') and g['origin']=='自动' for g in gs)}

@app.put('/api/attempts/{aid}')
def save_attempt(aid:str,body:dict):
    with store.connect() as c:
        row=c.execute('SELECT payload FROM attempts WHERE id=?',(aid,)).fetchone();require(row is not None,'练习不存在',404);a=json.loads(row[0])
        require(a['status']!='submitted','已提交练习不可覆盖，请新建重做',409);require(body.get('version')==a['version'],'另一页面已修改作答，请重新打开练习',409)
        responses=body.get('responses',a['responses']);p=store.paper(a['paper_id']);allowed={str(i['number']) for i in p['items']}
        require(isinstance(responses,dict) and set(responses)<=allowed,'作答题号不合法')
        require(all(isinstance(v,str) and len(v)<=10000 for v in responses.values()),'作答超过安全长度')
        delta=bounded(body.get('elapsed_delta',0),0,300,'本次活动秒数')
        if a['status']=='active':a['elapsed']+=delta
        state=body.get('status',a['status']);require(state in ('active','paused'),'练习状态不合法')
        a.update(responses=responses,status=state,version=a['version']+1)
        c.execute('UPDATE attempts SET version=?,status=?,payload=? WHERE id=?',(a['version'],state,dumps(a),aid))
    return a

@app.post('/api/attempts/{aid}/submit')
def submit(aid:str,body:dict):
    with store.connect() as c:
        row=c.execute('SELECT payload FROM attempts WHERE id=?',(aid,)).fetchone();require(row is not None,'练习不存在',404);a=json.loads(row[0])
        if a['status']=='submitted':return get_attempt(aid)
        require(body.get('version')==a['version'],'练习版本冲突，请刷新',409);p=store.paper(a['paper_id'])
        a['grades']={str(it['number']):grade(it['question'],a['responses'].get(str(it['number']),''),it['points']) for it in p['items']}
        a.update(status='submitted',version=a['version']+1,submitted_at=now())
        c.execute('UPDATE attempts SET status=?,version=?,payload=? WHERE id=?',('submitted',a['version'],dumps(a),aid));store.event(c,'attempt_submitted',{'id':aid})
    return get_attempt(aid)

@app.post('/api/attempts/{aid}/score')
def manual_score(aid:str,body:dict):
    with store.connect() as c:
        row=c.execute('SELECT payload FROM attempts WHERE id=?',(aid,)).fetchone();require(row is not None,'练习不存在',404);a=json.loads(row[0])
        require(a['status']=='submitted','提交后才能评分');require(body.get('version')==a['version'],'成绩已在另一页修改',409)
        n=str(body.get('number'));p=store.paper(a['paper_id']);it=next((x for x in p['items'] if str(x['number'])==n),None);require(it is not None,'题号不存在')
        score=body.get('score');require(isinstance(score,(int,float)) and not isinstance(score,bool) and it['points'] is not None and 0<=score<=it['points'],'评分应在0与该题分值之间；不计分题不能录分')
        origin=body.get('origin','自评');require(origin in ('自评','人工'),'评分来源不合法')
        a['score_history'].append({'number':n,'before':copy.deepcopy(a['grades'][n]),'score':score,'origin':origin,'date':now()})
        a['grades'][n].update(score=score,origin=origin,state='自评正确' if score==it['points'] else '部分得分' if score>0 else '错误',graded_at=now())
        a['version']+=1;c.execute('UPDATE attempts SET version=?,payload=? WHERE id=?',(a['version'],dumps(a),aid))
    return get_attempt(aid)

@app.get('/api/mistakes')
def mistakes():
    with store.connect() as c:rows=[json.loads(r[0]) for r in c.execute("SELECT payload FROM attempts WHERE status='submitted' ORDER BY created DESC")]
    result=[]
    for a in rows:
        p=store.paper(a['paper_id'])
        for it in p['items']:
            g=a['grades'][str(it['number'])]
            if g['state'] in ('错误','部分得分','待人工检查'):result.append({'attempt_id':a['id'],'paper_id':p['id'],'paper_title':p['title'],'number':it['number'],'question':it['question'],'grade':g,'date':a['created']})
    return result

def job_set(jid,state,payload):
    with store.connect() as c:
        row=c.execute('SELECT state FROM jobs WHERE id=?',(jid,)).fetchone()
        if row and row[0]=='cancelled' and state!='cancelled':return
        c.execute('UPDATE jobs SET state=?,payload=? WHERE id=?',(state,dumps(payload),jid))
def job_get(jid):
    with store.connect() as c:r=c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
    if not r:raise KeyError('任务不存在')
    return dict(json.loads(r['payload']),id=jid,state=r['state'])

def export_worker(jid,pid,base_url):
    try:
        from playwright.sync_api import sync_playwright
        p=display_paper(store.paper(pid));files=[]
        require(p['checks']['passed'],'当前排版校验未通过，停止导出')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            try:
                for kind,label in [('exam','试卷'),('answers','答案与解析')]:
                    if job_get(jid)['state']=='cancelled':return
                    page=browser.new_page(viewport={'width':900,'height':1100})
                    page.goto(f'{base_url}/?print={pid}&kind={kind}',wait_until='networkidle',timeout=60000)
                    page.wait_for_function('window.printReady === true',timeout=60000)
                    errors=page.locator('.math-error').all_text_contents();require(not errors,'公式显示失败，停止导出：'+'；'.join(errors[:3]))
                    path=unique(EXPORT,p['title']+'_'+label,'.pdf')
                    page.pdf(path=str(path),format='A4',margin={'top':'18mm','bottom':'18mm','left':'18mm','right':'18mm'},print_background=True,display_header_footer=True,
                             header_template='<span></span>',footer_template='<div style="font-size:9px;width:100%;text-align:center;color:#777">数学二练习资料 · <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
                    from pypdf import PdfReader
                    files.append({'name':path.name,'kind':kind,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'pages':len(PdfReader(path).pages)})
                    page.close();job_set(jid,'running',{'kind':'export','paper_id':pid,'files':files,'progress':len(files)*50})
            finally:browser.close()
        if job_get(jid)['state']=='cancelled':return
        manifest={'kind':'export','paper_id':pid,'paper_version':p['version'],'question_ids':[it['question']['id'] for it in p['items']],'snapshot_hash':digest(p),'files':files,'progress':100,'created':now()}
        unique(EXPORT,p['title']+'_导出记录','.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');job_set(jid,'done',manifest)
    except Exception as exc:
        logging.exception('PDF任务失败 %s',jid);job_set(jid,'failed',{'kind':'export','paper_id':pid,'error':str(exc)[:1000]})

@app.post('/api/papers/{pid}/export')
def export(pid:str,request:Request):
    p=display_paper(store.paper(pid));require(p['checks']['passed'],'存在硬约束或排版错误，不能导出合规卷')
    with store.connect() as c:
        for r in c.execute("SELECT id,payload FROM jobs WHERE state IN ('running','queued')"):
            if json.loads(r['payload']).get('paper_id')==pid:return {'id':r['id'],'duplicate':True}
        jid=uid('J');c.execute('INSERT INTO jobs VALUES(?,?,?)',(jid,'queued',dumps({'kind':'export','paper_id':pid,'progress':0})))
    threading.Thread(target=export_worker,args=(jid,pid,str(request.base_url).rstrip('/')),daemon=True).start()
    return {'id':jid}

@app.get('/api/jobs')
def jobs():
    with store.connect() as c:return [dict(json.loads(r['payload']),id=r['id'],state=r['state']) for r in c.execute('SELECT * FROM jobs ORDER BY rowid DESC LIMIT 20')]
@app.get('/api/jobs/{jid}')
def get_job(jid:str):return job_get(jid)
@app.post('/api/jobs/{jid}/cancel')
def cancel_job(jid:str):
    j=job_get(jid);require(j['state'] in ('queued','running'),'任务已经结束');job_set(jid,'cancelled',j);return {'cancelled':True}

@app.get('/api/download/{name}')
def download(name:str):
    p=(EXPORT/name).resolve();require(p.is_relative_to(EXPORT) and p.name==name and p.is_file(),'文件不存在或路径非法',404)
    return FileResponse(p,filename=p.name)

def make_backup():
    target=unique(BACKUP,'数学二_备份','.zip');temp=unique(BACKUP,'数据库快照','.sqlite3')
    with store.lock:
        with contextlib.closing(sqlite3.connect(store.path)) as src,contextlib.closing(sqlite3.connect(temp)) as dst:src.backup(dst)
        blob=temp.read_bytes();manifest={'schema':1,'app_version':VERSION,'created':now(),'sha256':hashlib.sha256(blob).hexdigest()}
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('database.sqlite3',blob);z.writestr('manifest.json',dumps(manifest))
        temp.unlink()
    return {'name':target.name,'manifest':manifest}

@app.post('/api/backup')
def backup():return make_backup()
@app.get('/api/backups')
def backups():return [{'name':p.name,'bytes':p.stat().st_size} for p in sorted(BACKUP.glob('*.zip'),key=lambda p:p.stat().st_mtime,reverse=True)]

@app.get('/api/backups/{name}')
def backup_download(name:str):
    p=(BACKUP/name).resolve();require(p.is_relative_to(BACKUP) and p.name==name and p.is_file(),'备份不存在',404);return FileResponse(p,filename=p.name)

@app.post('/api/restore')
def restore(body:dict):
    name=body.get('name','');path=(BACKUP/name).resolve();require(path.is_relative_to(BACKUP) and path.is_file() and path.name==name,'备份路径非法')
    require(path.stat().st_size<100*1024*1024,'归档超过100MB')
    try:
        with zipfile.ZipFile(path) as z:
            require(set(z.namelist())=={'database.sqlite3','manifest.json'},'备份含不允许的路径或文件')
            require(sum(x.file_size for x in z.infolist())<200*1024*1024,'解压后超过安全大小')
            m=json.loads(z.read('manifest.json'));blob=z.read('database.sqlite3')
        require(m.get('schema')==1 and m.get('sha256')==hashlib.sha256(blob).hexdigest(),'备份版本不兼容或指纹错误')
        tmp=unique(DATA,'恢复校验','.sqlite3');tmp.write_bytes(blob)
        try:
            with contextlib.closing(sqlite3.connect(tmp)) as c:
                require(c.execute('PRAGMA integrity_check').fetchone()[0]=='ok','备份数据库损坏')
                require(c.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0]=='1','数据库模式不兼容')
                expected={'questions','revisions','notes','papers','attempts','jobs','events','imports','tasks','candidates','candidate_history','review_records','model_calls'}
                require(expected<=set(r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")),'备份缺少必要数据表')
            with store.lock:
                with store.connect() as c:require(not c.execute("SELECT 1 FROM jobs WHERE state IN ('running','queued')").fetchone(),'任务执行中，请完成或取消后恢复',409)
                protected=make_backup()
                with contextlib.closing(sqlite3.connect(store.path)) as c:c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                os.replace(tmp,store.path)
        finally:
            if tmp.exists():tmp.unlink()
    except (zipfile.BadZipFile,json.JSONDecodeError,sqlite3.DatabaseError) as e:fail('损坏备份未恢复，当前数据保持完整：'+type(e).__name__)
    migrate_layout()
    return {'restored':True,'protected_backup':protected['name']}

def migrate_layout():
    """Backup first, append revisions, and leave source payloads/papers untouched."""
    rows=[q for q in store.questions() if q.get('presentation_version')!=LAYOUT_VERSION]
    if not rows:return
    protected=make_backup()
    pending=[]
    with store.connect() as c:
        for old in rows:
            q=prepare(old)
            for k in ('favorite','personal_note','note_version'):q.pop(k,None)
            q['previous_revision']=old['revision'];q['revision']=uid('R')
            layout_hash=digest({'source_hash':q['payload_hash'],'presentation':LAYOUT_VERSION})
            c.execute('INSERT INTO revisions VALUES(?,?,?,?,?)',(q['revision'],q['id'],layout_hash,now(),dumps(q)))
            c.execute('UPDATE questions SET current_rev=? WHERE id=?',(q['revision'],q['id']))
            if old.get('eligible') and not q.get('eligible'):pending.append(q['id'])
        store.event(c,'presentation_migration',{'version':LAYOUT_VERSION,'revisions':len(rows),'pending':pending,'protected_backup':protected['name']})

def bootstrap():
    migrate_layout()
    seed=APP_DIR/'assets'/'demo.json'
    if seed.exists():
        data=json.loads(seed.read_text(encoding='utf-8'));result=import_questions(parse_source(data,trusted_original=True),'项目原创演示22题',digest(data))
        with store.connect() as c:exists=c.execute("SELECT value FROM meta WHERE key='demo_paper'").fetchone()
        if not exists:
            qs={q['id']:q for q in store.questions()};items=[{'number':r['number'],'points':r['points'],'locked':False,'question':qs[r['ID']]} for r in sorted(data['questions'],key=lambda r:r['number'])]
            p=save_paper(paper_record('数学二原创示例卷（新卷02）','standard',items))
            with store.connect() as c:c.execute("INSERT INTO meta VALUES('demo_paper',?)",(p['id'],))
    with store.connect() as c:
        for row in c.execute("SELECT id,payload FROM jobs WHERE state IN ('running','queued')").fetchall():
            payload=json.loads(row['payload']);payload['error']='服务曾中断，任务未完成；请重新启动任务'
            c.execute("UPDATE jobs SET state='failed',payload=? WHERE id=?",(dumps(payload),row['id']))

bootstrap()
from .studio import create_router
app.include_router(create_router(store,import_questions,APP_DIR/'assets'/'命题依据'))
from .model import create_model_router
app.include_router(create_model_router(store,DATA,app))
frontend=APP_DIR/'frontend'/'dist'
if frontend.exists():app.mount('/',StaticFiles(directory=frontend,html=True),name='frontend')
