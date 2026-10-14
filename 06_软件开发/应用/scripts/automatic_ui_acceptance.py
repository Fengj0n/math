"""Real EXE, browser and loopback mock provider. No genuine AI quality claim."""
import pathlib,json,os,time,subprocess,threading,socket
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import httpx
from playwright.sync_api import sync_playwright
root=pathlib.Path(__file__).resolve().parents[2];out=root/'验收记录'/'AI自动审核界面';out.mkdir(exist_ok=True)
package=pathlib.Path(json.loads((root/'验收记录'/'最新Windows交付.json').read_text(encoding='utf-8'))['package'])
home=out/('隔离数据_'+time.strftime('%H%M%S'));prompts=[];checks=[]
sample={'stem':'设$f(x)=x^2$，则$f\u0027(1)=$（　）。','options':['$1$','$2$','$3$','$4$'],'parts':[],'answer':'A','solution':'合成错误答案仅用于功能验收；初版将函数值误作导数值，待模拟审题发现。','core':'导数法则','method':'直接求导','value':'仅验收测试，检测自动纠正函数值与导数值的混淆','misconception':'把函数值误作导数','source_difference':'这是隔离测试合成题，不代表新题质量或全库原创性','difficulty':1,'calculation':1,'minutes':2,'rubric':[],'reference_ids':[],'risk':'仅限测试；不得进入私人正式题库'}
gates=['数学正确性','答案唯一性或解集完整','条件充分与边界','范围','选项或评分','实质排重','公式显示','来源可靠']
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));prompt=body['messages'][0]['content'];prompts.append(prompt)
  if '只输出JSON对象' in prompt:
   value={'schema':'math2-candidates-1','candidates':[sample]}
  elif '你是数学二审题求解器' in prompt:
   data=json.loads(prompt.split('\n',1)[1]);assert not {'answer','solution','references'}&set(data)
   value={'answer':'B','solution':'模拟独立推导：函数x²的导数是2x，代入x=1得2，四个选项中只有B符合。','uncertain':False,'issues':[]}
  elif '你是数学二命题审核器' in prompt:
   data=json.loads(prompt.split('数据：',1)[1]);wrong=data['candidate']['answer']!='B'
   value={'decision':'修改' if wrong else '通过','uncertain':False,'answers_agree':not wrong,'gates':{g:True for g in gates},'evidence':{g:'本机模拟报告用于验证自动工作流；不构成真实数学质量评价。' for g in gates},'ratings':{'style':4,'value':4,'similarity':'低'},'note':'工程验收的模拟结论，测试数据隔离，不作为真实命题成果。'}
   if wrong:value['revised_candidate']=dict(sample,answer='B',solution='模拟修订：先求导f\u0027(x)=2x，再代入x=1得到2，故正确选项B。')
  else:raise ValueError('Unexpected provider request')
  encoded=json.dumps({'model':'loopback-mock','choices':[{'message':{'content':json.dumps(value,ensure_ascii=False)}}],'usage':{'total_tokens':100}},ensure_ascii=False).encode()
  self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
provider=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=provider.serve_forever,daemon=True).start()
for port in range(8765,8795):
 with socket.socket() as s:
  try:s.bind(('127.0.0.1',port));break
  except OSError:pass
base='http://127.0.0.1:'+str(port);env=os.environ.copy();env['MATH2_HOME']=str(home);env.pop('PLAYWRIGHT_BROWSERS_PATH',None)
log=(out/'服务日志.txt').open('w',encoding='utf-8');server=subprocess.Popen([str(package/'Math2Studio.exe'),'--no-browser'],cwd=package,env=env,stdout=log,stderr=log)
client=httpx.Client(base_url=base,timeout=30,trust_env=False);os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(root/'开发依赖'/'浏览器')
try:
 for _ in range(100):
  try:
   if client.get('/api/health').json()['version']=='1.2.0':break
  except Exception:pass
  time.sleep(.2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(base,wait_until='networkidle');page.get_by_role('button',name='数据与设置',exact=True).click()
  page.get_by_label('兼容 Chat Completions 的 API 地址').fill('http://127.0.0.1:'+str(provider.server_port)+'/v1');page.get_by_label('模型名称',exact=True).fill('loopback-mock')
  page.get_by_label('API 密钥（仅本机加密保存）',exact=True).fill('LOCAL-TEST-NOT-A-REAL-KEY');page.get_by_role('button',name='保存配置',exact=True).click();page.get_by_role('status').filter(has_text='模型配置已保存').wait_for()
  checks.append('真实EXE界面配置本机模拟API；未向外部供应商发请求')
  page.get_by_role('button',name='命题任务',exact=True).click();page.get_by_label('考查目标与拟暴露的误解').fill('隔离工程验收：生成一个错答案候选，自动纠错并重审入库；不代表真实质量。')
  page.get_by_role('button',name='保存命题任务',exact=True).click();page.get_by_role('button',name='调用已配置模型',exact=True).wait_for();page.get_by_role('button',name='调用已配置模型',exact=True).click()
  for _ in range(120):
   rows=client.get('/api/studio/candidates').json()
   if rows and rows[0]['state'] in ('AI自动审核入库','待人工检查','已淘汰'):break
   time.sleep(.5)
  assert rows[0]['state']=='AI自动审核入库',rows
  checks.append('点击生成后自动启动审核，无人工采纳操作')
  cid=rows[0]['id'];v=client.get('/api/studio/candidates/'+cid).json()
  assert v['version']==2 and v['raw']['answer']=='B' and len(v['auto_review']['history'])==2
  assert len(prompts)==7 and len(v['auto_review']['call_ids'])==6
  checks.append('发现初版A答案错误→自动修改为B→重新两次题面求解→自动入库')
  page.get_by_role('button',name='审题工作台',exact=True).click();page.locator('.candidate-card').first.click();page.get_by_role('heading',name='AI审题与修改 · 版本 2',exact=True).wait_for()
  assert page.get_by_role('button',name='AI自动审题与修改',exact=True).is_disabled()
  page.get_by_text('AI审核结论：通过',exact=True).wait_for();page.wait_for_timeout(1700);page.screenshot(path=str(out/'01_AI自动审核及修改记录.png'),full_page=True);checks.append('实际界面展示AI审核状态、历史与来源标记')
  q=client.get('/api/questions/'+v['bank_id']).json();assert q['source']=='AI自动审核原创题'
  response=client.post('/api/assemble',json={'source_mode':'original','locked':{'1':q['id']},'seed':'auto-ui','budget':1000});response.raise_for_status();draft=response.json()['paper'];assert draft['items'][0]['question']['id']==q['id']
  paper=client.post('/api/papers',json={'draft':draft,'title':'隔离验收自动审题卷'});paper.raise_for_status()
  checks.append('未经人工确认的AI通过题进入原创素材池并保存合规整卷')
  calls=client.get('/api/model/calls').json();assert len(calls)==7 and all(c['state']=='done' for c in calls)
  assert client.get('/api/dashboard').json()['questions']==23
  assert page.locator('.math-error').count()==0 and not errors,errors
  checks.append('七次真实本机HTTP调用均有输入输出审计；正式私人库未变')
  (out/'验收结果.json').write_text(json.dumps({'passed':True,'checks':checks,'provider':'本机HTTP模拟模型，不是真实AI审题质量验证','mock_calls':len(prompts),'candidate_version':v['version'],'candidate_state':v['state'],'database':str(home/'用户数据'/'math2.sqlite3'),'executable':str(package/'Math2Studio.exe'),'browser_errors':errors,'formula_render':'两个候选版本都经过冻结程序自带浏览器与KaTeX实际渲染'},ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'passed':True,'checks':len(checks),'mock_calls':len(prompts)},ensure_ascii=False));browser.close()
finally:server.terminate();server.wait(timeout=15);log.close();provider.shutdown();provider.server_close();client.close()
