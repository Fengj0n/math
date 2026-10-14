import copy,json
import pytest
from test_workflow import env,raw,candidate
from backend.auto_review import AutomaticReviewer,validate_report
from backend.studio import GATES
from backend.store import dumps

def report(decision='通过'):
 return {'decision':decision,'uncertain':False,'answers_agree':True,'gates':{g:True for g in GATES},'evidence':{g:'隔离测试的模拟审核依据：实际功能验收，不表示本题质量已验证。' for g in GATES},'ratings':{'style':4,'value':4,'similarity':'低'},'note':'模拟报告，仅验证自动流程，不在正式数据库生成真实命题成果。'}

def engine(m,monkeypatch,responder,render=True):
 from backend import auto_review
 monkeypatch.setattr(auto_review,'render_candidate_math',lambda *args:{'passed':render,'errors':[] if render else ['公式语法错误'],'method':'测试替身'})
 prompts=[]
 def invoke(op,prompt,tid,cancel):
  prompts.append((op,prompt));return json.dumps(responder(op,prompt,len(prompts)),ensure_ascii=False),'MOCK-'+str(len(prompts))
 return AutomaticReviewer(m.store,m.app,invoke,lambda:True),prompts

def result_value(op):
 return report() if op=='AI审题对照与修改' else {'answer':'B','solution':'独立测试推导：导数2x，代入1得2；四个选项仅B符合题意。','uncertain':False,'issues':[]}

def run(e,m,v):
 jid='test-job'
 with m.store.connect() as c:c.execute('INSERT INTO jobs VALUES(?,?,?)',(jid,'queued',dumps({'kind':'automatic_review','candidate_ids':[v['id']]})))
 e.worker(jid,[v['id']],'http://testserver')
 return e.candidate(v['id'])

def test_automatic_pass_no_human_confirmation(env,monkeypatch):
 c,m=env;v=candidate(c);e,p=engine(m,monkeypatch,lambda op,*_:result_value(op));new=run(e,m,v)
 assert new['state']=='AI自动审核入库'
 assert len(p)==3
 # The blind inputs contain no author answer, source or solution fields.
 for _,prompt in p[:2]:
  data=json.loads(prompt.split('\n',1)[1]);assert not {'answer','solution','references'}&set(data)
 q=c.get('/api/questions/'+new['bank_id']).json();assert q['source']=='AI自动审核原创题' and q['eligible']
 assert '未人工确认' in q['review']
 assembled=c.post('/api/assemble',json={'source_mode':'original','locked':{'1':q['id']},'seed':'auto','budget':1000}).json()
 assert assembled['paper']['items'][0]['question']['id']==q['id']
 assert c.post('/api/studio/candidates/'+v['id']+'/review',json={'decision':'通过','version':1}).status_code==409

def test_automatic_modify_then_resolve(env,monkeypatch):
 c,m=env;v=candidate(c)
 c.put('/api/studio/candidates/'+v['id'],json={'version':1,'raw':raw()|{'answer':'A'}})
 def response(op,prompt,n):
  r=result_value(op)
  if op=='AI审题对照与修改' and n==3:r=report('修改')|{'answers_agree':False,'revised_candidate':raw()}
  return r
 e,p=engine(m,monkeypatch,response);new=run(e,m,v)
 assert new['state']=='AI自动审核入库' and new['version']==3 and new['raw']['answer']=='B'
 assert len(p)==6 and len(new['auto_review']['history'])==2
 with m.store.connect() as db:assert db.execute('SELECT count(*) FROM candidate_history').fetchone()[0]==2

@pytest.mark.parametrize('fault',['uncertain','wrong_answer','low_quality','high_similarity','bad_gate','render_error'])
def test_automatic_fail_closed(env,monkeypatch,fault):
 c,m=env;v=candidate(c)
 def response(op,prompt,n):
  r=result_value(op)
  if op!='AI审题对照与修改':
   if fault=='uncertain':r['uncertain']=True
   if fault=='wrong_answer':r['answer']='C'
  else:
   if fault=='low_quality':r['ratings']['value']=3
   if fault=='high_similarity':r['ratings']['similarity']='高'
   if fault=='bad_gate':r['gates'][GATES[0]]=False
  return r
 e,p=engine(m,monkeypatch,response,render=fault!='render_error');new=run(e,m,v)
 assert new['state']=='待人工检查' and not new['bank_id']
 assert c.get('/api/dashboard').json()['questions']==22

def test_automatic_revision_budget(env,monkeypatch):
 c,m=env;v=candidate(c)
 def response(op,prompt,n):return report('修改')|{'revised_candidate':raw()|{'value':'测试第'+str(n)+'版修改，验证有界循环'}} if op=='AI审题对照与修改' else result_value(op)
 e,p=engine(m,monkeypatch,response);new=run(e,m,v)
 assert len(p)==9 and new['version']==3 and new['state']=='待人工检查' and not new['bank_id']

def test_automatic_cancel_cannot_admit(env,monkeypatch):
 c,m=env;v=candidate(c)
 def response(op,prompt,n):
  with m.store.connect() as db:db.execute("UPDATE jobs SET state='cancelled' WHERE id='test-job'")
  return result_value(op)
 e,p=engine(m,monkeypatch,response);new=run(e,m,v)
 assert len(p)==1 and new['state']=='待人工检查' and not new['bank_id']
 with m.store.connect() as db:assert db.execute("SELECT state FROM jobs WHERE id='test-job'").fetchone()[0]=='cancelled'

def test_auto_endpoint_without_key_and_forged_report(env):
 c,m=env;v=candidate(c)
 r=c.post('/api/model/auto-review',json={'candidate_ids':[v['id']],'gates':{g:True for g in GATES}})
 assert r.status_code==400 and c.get('/api/dashboard').json()['questions']==22
 with pytest.raises(ValueError):validate_report(report()|{'evidence':{g:'已检查' for g in GATES}})
