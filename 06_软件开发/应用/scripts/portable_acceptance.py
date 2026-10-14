"""Exercise the actual frozen EXE from a copied folder containing Chinese and spaces."""
import os,json,time,pathlib,subprocess,shutil,hashlib,socket
import httpx
from pypdf import PdfReader
from playwright.sync_api import sync_playwright
root=pathlib.Path(__file__).resolve().parents[2]
evidence=root/'验收记录'/'便携验收';evidence.mkdir(parents=True,exist_ok=True)
manifest=json.loads((root/'验收记录'/'最新Windows交付.json').read_text(encoding='utf-8-sig'))
origin=pathlib.Path(manifest['package']);copied=evidence/('中文 空格独立运行_'+time.strftime('%H%M%S'))/'Math2Studio'
shutil.copytree(origin,copied)
ports=[]
for port in range(8765,8795):
 with socket.socket() as s:
  try:s.bind(('127.0.0.1',port));ports.append(port)
  except OSError:pass
base='http://127.0.0.1:'+str(ports[0]);env=os.environ.copy()
env.pop('MATH2_HOME',None);env.pop('PLAYWRIGHT_BROWSERS_PATH',None)
env['PATH']=os.environ['SystemRoot']+'\\System32;'+os.environ['SystemRoot']
log=(evidence/'EXE日志.txt').open('w',encoding='utf-8')
process=subprocess.Popen([str(copied/'Math2Studio.exe'),'--no-browser'],cwd=copied,env=env,stdout=log,stderr=log)
client=httpx.Client(base_url=base,timeout=30,trust_env=False);checks=[]
def get(path):
 r=client.get(path);r.raise_for_status();return r.json()
try:
 for _ in range(100):
  try:
   if get('/api/health')['version']=='1.0.0':break
  except Exception:pass
  if process.poll() is not None:raise RuntimeError('EXE提前退出，请检查EXE日志')
  time.sleep(.2)
 else:raise RuntimeError('启动超时')
 checks.append('复制到中文带空格目录，移除开发工具PATH后，真实EXE启动')
 dash=get('/api/dashboard');assert dash['questions']==1244,dash
 assert get('/api/studio/summary')['approved']==0
 assert not get('/api/data/info')['project_available']
 checks.append('1244条私人资料副本，未混入合成审核题，无作者上游目录依赖')
 body={'subject':'高等数学','type':'选择题','chapter':'一元函数微分学','target':'便携验收：检验导数性质与条件判定，保持参考来源可追溯。','difficulty':3,'candidate_count':3}
 task=client.post('/api/studio/tasks',json=body);task.raise_for_status();task=task.json()
 assert len(task['policy_evidence'])==4
 checks.append('真实EXE读取四份命题依据摘录并保存任务')
 paper=next(p for p in get('/api/papers') if '原创示例卷' in p['title'])
 detail=get('/api/papers/'+paper['id']);assert detail['checks']['passed']
 assert len(detail['items'])==22 and sum(x['points'] for x in detail['items'])==150
 exam=get('/api/papers/'+paper['id']+'?exam=true')
 assert all('answer' not in x['question'] and 'solution' not in x['question'] for x in exam['items'])
 checks.append('正式结构22题150分与试卷接口答案隔离')
 response=client.post('/api/papers/'+paper['id']+'/export');response.raise_for_status();jid=response.json()['id']
 for _ in range(120):
  job=get('/api/jobs/'+jid)
  if job['state'] in ('done','failed','cancelled'):break
  time.sleep(.5)
 assert job['state']=='done',job
 output=root/'交付'/'试用示例';output.mkdir(parents=True,exist_ok=True);files=[]
 for f in job['files']:
  content=client.get('/api/download/'+f['name']);content.raise_for_status()
  name='数学二原创示例_'+('试卷' if f['kind']=='exam' else '标准答案与解析')+'.pdf';path=output/name
  path.write_bytes(content.content);pages=len(PdfReader(path).pages)
  assert hashlib.sha256(content.content).hexdigest()==f['sha256'] and pages==f['pages']
  files.append(dict(path=str(path),pages=pages,sha256=f['sha256'],kind=f['kind']))
 checks.append('EXE自带Chromium实际导出双份PDF并验证页数与指纹')
 os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(root/'开发依赖'/'浏览器')
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base,wait_until='networkidle')
  page.get_by_role('heading',name='总览',exact=True).wait_for();page.screenshot(path=str(evidence/'便携首页.png'),full_page=True)
  for kind in ('exam','answers'):
   page.goto(base+'/?print='+paper['id']+'&kind='+kind,wait_until='networkidle');page.wait_for_function('window.printReady === true')
   assert page.locator('.math-error').count()==0
   assert page.locator('.print-prompt').count()==22
  assert not errors,errors;browser.close()
 checks.append('冻结软件前端实际加载；22题公式渲染零错误，题面与题号统一分页组')
 response=client.post('/api/backup');response.raise_for_status();checks.append('便携软件SQLite一致性备份')
 (evidence/'验收结果.json').write_text(json.dumps({'passed':True,'checks':checks,'dashboard':dash,'pdfs':files,'tested_executable':str(copied/'Math2Studio.exe'),'source_package':str(origin),'browser_errors':errors,'limits':['仅本机Windows实测；未在另一台干净电脑实测','未配置真实模型供应商密钥']},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'passed':True,'checks':len(checks),'pdfs':files},ensure_ascii=False))
finally:
 process.terminate();process.wait(timeout=15);log.close();client.close()
