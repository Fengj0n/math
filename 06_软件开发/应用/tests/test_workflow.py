import os,json,importlib,copy,time,hashlib,zipfile
from pathlib import Path
import pytest,httpx
from fastapi.testclient import TestClient

@pytest.fixture
def env(tmp_path,monkeypatch):
 monkeypatch.setenv('MATH2_HOME',str(tmp_path))
 from backend import main
 main=importlib.reload(main)
 with TestClient(main.app) as client:yield client,main

def task(c):
 r=c.post('/api/studio/tasks',json={'chapter':'一元函数微分学','target':'考查导数定义与瞬时变化率的理解','type':'选择题'})
 assert r.status_code==200,r.text
 return r.json()

def raw():return {'stem':'设$f(x)=x^2$，则$f\u0027(1)=$（　）。','options':['$1$','$2$','$3$','$4$'],'parts':[],'answer':'B','solution':'由导数定义或求导法则，f\u0027(x)=2x，故f\u0027(1)=2。','core':'导数','method':'求导法则','value':'检测是否将函数值误认为导数值','misconception':'用函数值1替代导数值2','source_difference':'测试用合成数据，不用于真实命题质量证明','difficulty':1,'calculation':1,'minutes':2,'rubric':[],'risk':'测试数据','reference_ids':[]}

def candidate(c,t=None):
 t=t or task(c);r=c.post(f"/api/studio/tasks/{t['id']}/candidates",json={'schema':'math2-candidates-1','candidates':[raw()]})
 assert r.status_code==200,r.text
 return r.json()['candidates'][0]

def approve(c,v):
 from backend.studio import GATES
 derivation='独立重解：由f(x)=x²得到f\u0027(x)=2x，代入x=1得到2，选B。'
 assert c.post(f"/api/studio/candidates/{v['id']}/derivation",json={'version':v['version'],'derivation':derivation}).status_code==200
 return c.post(f"/api/studio/candidates/{v['id']}/review",json={'version':v['version'],'decision':'通过','gates':{g:True for g in GATES},'derivation':derivation,'note':'测试人工采纳依据，确认合成测试题所有检查项','ratings':{'style':3,'value':3,'similarity':'低'}})

def test_seed_and_structure(env):
 c,m=env;d=c.get('/api/dashboard').json();assert d['questions']==22 and d['eligible']==22
 p=c.get('/api/papers').json()[0];assert p['checks']['count']==22 and p['checks']['points']==150 and p['checks']['subjects']=={'高等数学':118,'线性代数':32}

def test_real_source_idempotency_and_readonly(env):
 c,m=env;p=Path(r'D:\数学二\02_题库\数学二题库.json');before=hashlib.sha256(p.read_bytes()).hexdigest();data=json.loads(p.read_text(encoding='utf-8-sig'))
 for i in range(2):
  v=c.post('/api/import/preview',json={'data':data,'name':p.name}).json();assert v['count']==1222
  r=c.post('/api/import/commit',json={'token':v['token']});assert r.status_code==200
  if i:assert r.json()['duplicate'] is True
 assert c.get('/api/dashboard').json()['questions']==1244
 assert hashlib.sha256(p.read_bytes()).hexdigest()==before

def test_external_english_payload_cannot_claim_review(env):
 c,m=env;x=dict(raw(),ID='FORGED',type='选择题',points=5,subject='高等数学',chapter='一元函数微分学')
 p=c.post('/api/import/preview',json={'data':{'questions':[x]}}).json();assert p['eligible']==0

def test_blind_api_and_compare_order(env):
 c,m=env;v=candidate(c);b=c.get(f"/api/studio/candidates/{v['id']}/blind").json()
 assert not any(k in b for k in ('answer','solution','raw','rubric','references'))
 queue=c.get('/api/studio/candidates').json();assert 'raw' not in queue[0] and 'answer' not in queue[0]
 assert c.get(f"/api/studio/candidates/{v['id']}/compare").status_code==409
 assert approve(c,v).status_code==200
 assert c.get(f"/api/studio/candidates/{v['id']}/compare").status_code==200

@pytest.mark.parametrize('change',[{'options':['1','2']},{'difficulty':True},{'minutes':-1},{'reference_ids':['INVENTED']},{'solution':''}])
def test_invalid_candidate_is_atomic(env,change):
 c,m=env;t=task(c);bad=raw()|change
 r=c.post(f"/api/studio/tasks/{t['id']}/candidates",json={'schema':'math2-candidates-1','candidates':[raw(),bad]})
 assert r.status_code==400 and c.get('/api/studio/candidates').json()==[]

def test_candidate_import_duplicate_and_edit_conflict(env):
 c,m=env;t=task(c);v=candidate(c,t);r=c.post(f"/api/studio/tasks/{t['id']}/candidates",json={'schema':'math2-candidates-1','candidates':[raw(),raw()]}).json();assert r['added']==0 and r['duplicates']==2
 edited=raw()|{'value':'改进后的诊断目标与误解说明'}
 assert c.put(f"/api/studio/candidates/{v['id']}",json={'version':1,'raw':edited}).status_code==200
 assert c.put(f"/api/studio/candidates/{v['id']}",json={'version':1,'raw':edited}).status_code==409
 assert c.get(f"/api/studio/candidates/{v['id']}/blind").json()['saved_derivation']==''

def test_gates_and_admission_idempotency(env):
 c,m=env;v=candidate(c)
 assert c.post(f"/api/studio/candidates/{v['id']}/review",json={'version':1,'decision':'通过','gates':{}}).status_code==400
 r=approve(c,v);assert r.status_code==200,r.text;qid=r.json()['bank_id'];q=c.get('/api/questions/'+qid).json();assert q['eligible'] and q['source']=='审核后原创题'
 assert approve(c,v).status_code==409
 assert c.get('/api/dashboard').json()['questions']==23

def test_original_assembly_reproducible_and_lock(env):
 c,m=env;a=c.post('/api/assemble',json={'source_mode':'original','seed':'stable','budget':100}).json();b=c.post('/api/assemble',json={'source_mode':'original','seed':'stable','budget':100}).json()
 ids=lambda p:[i['question']['id'] for i in p['paper']['items']]
 assert ids(a)==ids(b);assert all(i['question']['source']=='项目原创示例' for i in a['paper']['items'])
 lock={'1':ids(a)[0]};r=c.post('/api/assemble',json={'locked':lock,'seed':'different','budget':100}).json();assert ids(r)[0]==lock['1']
 assert c.post('/api/assemble',json={'locked':{'1':'MISSING'}}).json()['status']=='候选不足'

def test_immutable_snapshot_and_forged_answer(env):
 c,m=env;a=c.post('/api/assemble',json={'budget':100}).json()['paper'];a['items'][0]['question']['answer']='HACK'
 p=c.post('/api/papers',json={'draft':a}).json();assert p['items'][0]['question']['answer']!='HACK'
 original=p['items'][0]['question'];r=c.post('/api/questions/'+original['id']+'/edit-copy',json={'revision':original['revision'],'fields':{'题干':'更改后的个人副本'}});assert r.status_code==200
 old=c.get('/api/papers/'+p['id']).json();assert old['items'][0]['question']['stem']==original['stem']
 exam=c.get('/api/papers/'+p['id']+'?exam=true').json();assert 'answer' not in exam['items'][0]['question'] and 'raw_payload' not in exam['items'][0]['question']

def test_backup_restore_and_corruption(env):
 c,m=env;v=candidate(c);backup=c.post('/api/backup').json();assert backup['name']
 result=c.post('/api/restore',json={'name':backup['name']});assert result.status_code==200,result.text
 assert c.get('/api/studio/candidates').json()[0]['id']==v['id']
 broken=m.BACKUP/'broken.zip';broken.write_bytes(b'invalid')
 assert c.post('/api/restore',json={'name':'broken.zip'}).status_code==400
 assert len(c.get('/api/studio/candidates').json())==1

def test_host_origin_and_path_bounds(env):
 c,m=env;assert c.get('/api/health',headers={'host':'remote.invalid'}).status_code==403
 assert c.post('/api/backup',headers={'origin':'https://evil.invalid'}).status_code==403
 assert c.get('/api/download/not-exists.pdf').status_code==404
 assert c.post('/api/restore',json={'name':'../outside.zip'}).status_code==400

def test_safe_numeric_grading():
 from backend.domain import numeric,grade
 assert numeric('__import__("os").system("bad")') is None and numeric('1/0') is None
 q={'type':'填空题','answer':'1/2'};assert grade(q,'0.5',5)['score']==5
 q={'type':'填空题','answer':'sin(x)'};assert grade(q,'sin(x)',5)['state']=='待人工检查'

def test_model_dpapi_and_real_call_mock(env,monkeypatch):
 c,m=env;from backend import model
 class FakeClient:
  def __init__(self,**kw):pass
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def post(self,url,**kwargs):return httpx.Response(200,json={'choices':[{'message':{'content':'CONNECTION_OK'}}],'model':'test-model','usage':{'total_tokens':7}})
 monkeypatch.setattr(model.httpx,'Client',FakeClient)
 r=c.put('/api/model/settings',json={'base_url':'https://example.invalid/v1','model':'test-model','api_key':'test-secret-key','timeout':10,'max_output_tokens':500});assert r.status_code==200
 assert 'test-secret-key' not in (m.DATA/'模型凭据.dpapi').read_bytes().decode('latin1')
 assert 'api_key' not in c.get('/api/model/settings').json()
 r=c.post('/api/model/test');assert r.status_code==200,r.text
 history=c.get('/api/model/calls').json();assert history[0]['state']=='done' and history[0]['usage']['total_tokens']==7
 assert 'test-secret-key' not in json.dumps(history)

def test_cancelled_jobs_not_overwritten(env):
 c,m=env
 with m.store.connect() as conn:conn.execute('INSERT INTO jobs VALUES(?,?,?)',('CANCEL_TEST','cancelled','{}'))
 m.job_set('CANCEL_TEST','done',{'files':['unexpected']});assert m.job_get('CANCEL_TEST')['state']=='cancelled'

def test_policy_evidence_and_choice_key(env):
 c,m=env;t=task(c);assert len(t['policy_evidence'])==4
 p=c.get(f"/api/studio/tasks/{t['id']}/prompt").json();assert '880高价值题型分析.md' in p['prompt'] and '实际摘读' in p['prompt']
 bad=raw()|{'answer':'BAD'};assert c.post(f"/api/studio/tasks/{t['id']}/candidates",json={'schema':'math2-candidates-1','candidates':[bad]}).status_code==400

def test_model_generation_job_and_blind_scope(env,monkeypatch):
 c,m=env;from backend import model
 prompts=[]
 class FakeClient:
  def __init__(self,**kw):pass
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def post(self,url,**kwargs):
   prompt=kwargs['json']['messages'][0]['content'];prompts.append(prompt)
   output=json.dumps({'schema':'math2-candidates-1','candidates':[raw()]}) if '只输出JSON对象' in prompt else '独立重解：对函数x²求导得到2x，代入x=1得到2，选B。'
   return httpx.Response(200,json={'choices':[{'message':{'content':output}}],'model':'mock-model','usage':{'total_tokens':40}})
 monkeypatch.setattr(model.httpx,'Client',FakeClient)
 assert c.put('/api/model/settings',json={'base_url':'https://example.invalid/v1','model':'mock-model','api_key':'test-key','timeout':10,'max_output_tokens':500}).status_code==200
 t=task(c);jid=c.post(f"/api/model/tasks/{t['id']}/generate").json()['id']
 for _ in range(60):
  j=c.get('/api/jobs/'+jid).json()
  if j['state'] not in ('queued','running'):break
  time.sleep(.05)
 assert j['state']=='done',j
 for _ in range(60):
  if not any(x['state'] in ('queued','running') for x in c.get('/api/jobs').json()):break
  time.sleep(.05)
 v=c.get('/api/studio/candidates').json()[0];r=c.post(f"/api/model/candidates/{v['id']}/solve");assert r.status_code==200,r.text
 blind_prompt=prompts[-1];assert '"answer"' not in blind_prompt and '"solution"' not in blind_prompt and '"references"' not in blind_prompt
 record=c.get('/api/model/calls/'+j['call_id']).json();assert record['output'] and record['input_hash']
