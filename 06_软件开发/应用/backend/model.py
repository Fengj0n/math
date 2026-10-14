"""Explicit compatible API calls. Credentials protected by Windows DPAPI, never in exports."""
import ctypes,json,time,datetime,urllib.parse,threading
from ctypes import wintypes
import httpx
from fastapi import APIRouter,HTTPException,Request
from .store import dumps,uid,now
from .domain import digest
from .auto_review import AutomaticReviewer,create_auto_router

class Blob(ctypes.Structure):
    _fields_=[('length',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]

def protect(data,decrypt=False):
    if not hasattr(ctypes,'windll'):raise ValueError('凭据存储仅支持Windows；其他系统使用外部候选导入')
    buf=ctypes.create_string_buffer(data);src=Blob(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)));out=Blob()
    if decrypt:ok=ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src),None,None,None,None,1,ctypes.byref(out))
    else:ok=ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src),'Math2Studio',None,None,None,1,ctypes.byref(out))
    if not ok:raise ValueError('Windows凭据加密或解密失败')
    try:return ctypes.string_at(out.data,out.length)
    finally:ctypes.windll.kernel32.LocalFree(out.data)

def create_model_router(store,data,app):
    router=APIRouter(prefix='/api/model');secret=data/'模型凭据.dpapi'
    with store.connect() as c:c.execute('CREATE TABLE IF NOT EXISTS model_calls(id TEXT PRIMARY KEY,created TEXT NOT NULL,payload TEXT NOT NULL)')
    def fail(ok,msg,status=400):
        if not ok:raise HTTPException(status,detail=msg)
    def settings():
        with store.connect() as c:r=c.execute("SELECT value FROM meta WHERE key='model_settings'").fetchone()
        if r:
            s=json.loads(r[0]);s['has_key']=bool(s.get('has_key') and secret.exists());return s
        return {'base_url':'https://api.openai.com/v1','model':'','has_key':False,'max_output_tokens':5000,'timeout':90,'daily_call_limit':10}
    def route(path,method):return next(r.endpoint for r in app.routes if getattr(r,'path',None)==path and method in getattr(r,'methods',set()))
    def record(value):
        with store.connect() as c:c.execute('INSERT OR REPLACE INTO model_calls VALUES(?,?,?)',(value['id'],value['created'],dumps(value)))
    def invoke(operation,prompt,task_id=None,cancel=lambda:False):
        fail(not cancel(),'任务已取消',409)
        s=settings();fail(s.get('has_key') and secret.exists() and s.get('model'),'请先保存API配置和模型名')
        day=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        with store.connect() as c:
            n=c.execute('SELECT count(*) FROM model_calls WHERE created LIKE ?',(day+'%',)).fetchone()[0]
            fail(n<s.get('daily_call_limit',10),'达到今日调用次数上限；不自动继续付费调用',429)
            call={'id':uid('CALL'),'created':now(),'operation':operation,'task_id':task_id,'model':s['model'],'base_url':s['base_url'],'prompt':prompt,'input_hash':digest(prompt),'state':'running','usage':None,'cost':None,'pricing_status':'未配置真实定价，不猜测费用','retries':0}
            c.execute('INSERT INTO model_calls VALUES(?,?,?)',(call['id'],call['created'],dumps(call)))
        start=time.monotonic()
        try:
            key=protect(secret.read_bytes(),True).decode('utf-8')
            with httpx.Client(timeout=s['timeout'],follow_redirects=False,trust_env=False) as client:
                response=client.post(s['base_url'].rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key},json={'model':s['model'],'messages':[{'role':'user','content':prompt}],'max_tokens':s['max_output_tokens']})
            fail(response.status_code==200,f'模型请求失败：HTTP {response.status_code}；没有重试',502)
            fail(len(response.content)<=2*1024*1024,'模型输出超过2MB，已隔离',502)
            value=response.json();output=value['choices'][0]['message']['content'];fail(isinstance(output,str),'模型未返回文本内容',502)
            call.update(state='done',output=output,usage=value.get('usage'),returned_model=value.get('model'),elapsed_seconds=round(time.monotonic()-start,2));record(call);return output,call['id']
        except Exception as e:
            call.update(state='failed',elapsed_seconds=round(time.monotonic()-start,2),error_type=type(e).__name__);record(call)
            if isinstance(e,HTTPException):raise
            raise HTTPException(502,detail='模型调用失败：'+type(e).__name__+'；记录已保存，没有自动重试')
    @router.get('/settings')
    def get_settings():return settings()
    @router.put('/settings')
    def put_settings(body:dict):
        url=str(body.get('base_url','')).strip().rstrip('/');p=urllib.parse.urlsplit(url)
        fail(p.hostname and not p.username and not p.password and not p.query and not p.fragment,'API地址不得包含凭据、查询参数或片段')
        fail(p.scheme=='https' or (p.scheme=='http' and p.hostname in ('localhost','127.0.0.1')),'远程API须HTTPS；HTTP仅支持本机服务')
        model=str(body.get('model','')).strip();fail(0<len(model)<=120,'请输入模型名称')
        timeout=body.get('timeout',90);tokens=body.get('max_output_tokens',5000)
        fail(type(timeout) is int and 10<=timeout<=180,'超时须为10—180秒');fail(type(tokens) is int and 500<=tokens<=16000,'输出tokens须为500—16000')
        key=body.get('api_key','');fail(isinstance(key,str) and len(key)<=4096,'密钥格式不合法')
        old=settings();fail(key.strip() or secret.exists(),'请在本机设置页输入密钥')
        if key.strip():secret.write_bytes(protect(key.strip().encode()))
        s={'base_url':url,'model':model,'has_key':True,'max_output_tokens':tokens,'timeout':timeout,'daily_call_limit':10}
        with store.connect() as c:c.execute("INSERT INTO meta VALUES('model_settings',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(dumps(s),))
        return s
    @router.get('/calls')
    def calls():
        with store.connect() as c:rows=[json.loads(r[0]) for r in c.execute('SELECT payload FROM model_calls ORDER BY created DESC LIMIT 50')]
        return [{k:r.get(k) for k in ('id','created','operation','task_id','model','returned_model','state','usage','elapsed_seconds','error_type','cost','pricing_status')} for r in rows]
    @router.get('/calls/{cid}')
    def call_detail(cid:str):
        with store.connect() as c:r=c.execute('SELECT payload FROM model_calls WHERE id=?',(cid,)).fetchone()
        fail(r is not None,'调用记录不存在',404);return json.loads(r[0])
    @router.post('/test')
    def test():
        output,cid=invoke('连接测试','请只回复 CONNECTION_OK。')
        return {'message':'服务返回了实际响应；调用记录已保存。返回内容：'+output[:100],'call_id':cid}
    def generation_worker(tid,jid,prompt,base_url):
        def cancelled():
            with store.connect() as c:r=c.execute('SELECT state FROM jobs WHERE id=?',(jid,)).fetchone()
            return not r or r[0]=='cancelled'
        def update(state,value):
            with store.connect() as c:
                if not cancelled():c.execute('UPDATE jobs SET state=?,payload=? WHERE id=?',(state,dumps({'kind':'model_generation','task_id':tid,**value}),jid))
        try:
            update('running',{'progress':10,'stage':'等待模型响应（不代表实际token进度）'})
            output,cid=invoke('原创候选生成',prompt['prompt'],tid,cancelled)
            if cancelled():return
            text=output.strip()
            if text.startswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
            try:body=json.loads(text)
            except (ValueError,IndexError):raise HTTPException(422,detail='模型JSON无法可靠解析，输出已保留；未猜补或入库')
            with store.connect() as c:
                if cancelled():return
                result=route('/api/studio/tasks/{tid}/candidates','POST')(tid,body)
                for v in result['candidates']:
                    v['call_id']=cid;v['import_origin']='本软件真实API调用；实际模型记录见'+cid
                    c.execute('UPDATE candidates SET payload=? WHERE id=?',(dumps(v),v['id']))
                c.execute('UPDATE jobs SET state=?,payload=? WHERE id=?',('done',dumps({'kind':'model_generation','task_id':tid,'progress':100,'added':result['added'],'duplicates':result['duplicates'],'call_id':cid}),jid))
            if result['candidates'] and not cancelled():
                review_job=reviewer.start([v['id'] for v in result['candidates']],base_url)
                update('done',{'progress':100,'added':result['added'],'duplicates':result['duplicates'],'call_id':cid,'auto_review_job':review_job['id']})
        except Exception as e:update('failed',{'error':str(getattr(e,'detail',type(e).__name__))[:600],'progress':0})
    @router.post('/tasks/{tid}/generate')
    def generate(tid:str,request:Request):
        prompt=route('/api/studio/tasks/{tid}/prompt','GET')(tid)
        with store.connect() as c:
            existing=c.execute("SELECT id,payload FROM jobs WHERE state IN ('queued','running')").fetchall()
            for r in existing:
                if json.loads(r['payload']).get('task_id')==tid:return {'id':r['id'],'duplicate':True}
            jid=uid('J');c.execute('INSERT INTO jobs VALUES(?,?,?)',(jid,'queued',dumps({'kind':'model_generation','task_id':tid,'progress':0})))
        threading.Thread(target=generation_worker,args=(tid,jid,prompt,str(request.base_url).rstrip('/')),daemon=True).start()
        return {'id':jid}
    @router.post('/candidates/{cid}/solve')
    def solve(cid:str):
        blind=route('/api/studio/candidates/{cid}/blind','GET')(cid)
        blind={k:blind[k] for k in ('candidate_id','version','type','points','stem','options','parts')}
        prompt='仅根据以下题面独立求解，保存完整推导，检查边界、条件和唯一性。未知写待人工检查。你没有收到作者答案。\n'+dumps(blind)
        output,call_id=invoke('题面独立求解',prompt)
        return {'candidate_id':cid,'version':blind['version'],'derivation':output,'call_id':call_id,'status':'模型重解建议，不能作为数学无误证明'}
    reviewer=AutomaticReviewer(store,app,invoke,lambda:bool(settings().get('has_key') and settings().get('model')))
    router.include_router(create_auto_router(reviewer),prefix='')
    return router
