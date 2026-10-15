"""Real browser workflow on an isolated database; all artifacts stay under software folder."""
import os,sys,json,time,subprocess,pathlib,hashlib
import httpx
from playwright.sync_api import sync_playwright
root=pathlib.Path(__file__).resolve().parents[2];appdir=root/'应用';evidence=root/'验收记录';out=evidence/'界面';out.mkdir(parents=True,exist_ok=True)
env=os.environ.copy();env['MATH2_HOME']=str(evidence/('界面测试数据_'+time.strftime('%Y%m%d_%H%M%S')));env['PLAYWRIGHT_BROWSERS_PATH']=str(root/'开发依赖'/'浏览器');env['PYTHONIOENCODING']='utf-8'
os.environ['PLAYWRIGHT_BROWSERS_PATH']=env['PLAYWRIGHT_BROWSERS_PATH']
log=(out/'server.log').open('w',encoding='utf-8');server=subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8780'],cwd=appdir,env=env,stdout=log,stderr=log)
checks=[];base='http://127.0.0.1:8780';client=httpx.Client(base_url=base,timeout=30)
try:
 for _ in range(80):
  try:
   if client.get('/api/health').status_code==200:break
  except httpx.HTTPError:pass
  time.sleep(.2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(base,wait_until='networkidle');page.get_by_role('heading',name='总览',exact=True).wait_for();page.screenshot(path=str(out/'01_总览.png'),full_page=True);checks.append('首页真实数据与本地资源加载')
  page.get_by_role('button',name='数据与设置',exact=True).click();page.get_by_label('资料JSON文件').set_input_files(str(root.parent/'02_题库'/'数学二题库.json'));page.get_by_role('button',name='确认导入副本',exact=True).wait_for();page.get_by_role('button',name='确认导入副本',exact=True).click();page.get_by_role('status').filter(has_text='新增1222条').wait_for();checks.append('真实1222条资料通过界面导入副本')
  page.get_by_role('button',name='题库',exact=True).click();page.get_by_label('核验筛选').select_option('eligible');page.get_by_label('搜索题库').fill('导数');page.wait_for_timeout(700);page.screenshot(path=str(out/'02_题库.png'),full_page=True);checks.append('题库搜索与可用状态筛选')
  page.get_by_role('button',name='命题任务',exact=True).click();page.get_by_label('考查目标与拟暴露的误解').fill('验收测试：考查导数法则与函数值的区别，测试记录不用于真实命题。');page.get_by_role('button',name='保存命题任务',exact=True).click();page.get_by_role('heading',name='导入外部候选结果').wait_for()
  raw={'stem':'设$f(x)=x^2$，则$f\u0027(1)=$（　）。','options':['$1$','$2$','$3$','$4$'],'parts':[],'answer':'B','solution':'求导得到f\u0027(x)=2x，代入x=1得2，标准答案B。','core':'导数法则','method':'直接求导','value':'仅用于验收测试，检测导数与函数值混淆','misconception':'把函数值作为导数','source_difference':'验收用合成题，不声称原创质量或与真题同水平','difficulty':1,'calculation':1,'minutes':2,'rubric':[],'reference_ids':[],'risk':'测试题，应排除真实命题素材池'}
  page.get_by_label('候选JSON内容').fill(json.dumps({'schema':'math2-candidates-1','candidates':[raw]},ensure_ascii=False));page.get_by_role('button',name='校验并保存候选',exact=True).click();page.get_by_role('status').filter(has_text='新增1道').wait_for();page.screenshot(path=str(out/'03_命题任务.png'),full_page=True)
  page.get_by_role('button',name='审题工作台',exact=True).click();page.locator('.candidate-card').first.click();page.get_by_label('独立重解推导（先保存，再对照）').wait_for();assert page.get_by_role('heading',name='作者答案与完整解答').count()==0;checks.append('题面阶段未展示或预取作者答案')
  page.get_by_label('独立重解推导（先保存，再对照）').fill('独立重解：函数为x²，导数为2x，在x=1处导数值2。四个选项恰好B符合。');page.get_by_role('button',name='保存推导并对照',exact=True).click();page.get_by_role('heading',name='作者答案与完整解答').wait_for()
  for gate in ['数学正确性','答案唯一性或解集完整','条件充分与边界','范围','选项或评分','实质排重','公式显示','来源可靠']:page.get_by_label(gate,exact=True).check()
  page.get_by_label('相似风险',exact=True).select_option('低');page.get_by_label('对照差异、处理与采纳依据').fill('验收测试人工确认；合成数据仅保存于独立测试数据库。');page.get_by_role('button',name='人工审核采纳',exact=True).click();page.get_by_role('status').filter(has_text='人工审核已保存').wait_for();page.screenshot(path=str(out/'04_审题工作台.png'),full_page=True);checks.append('保存推导→对照→八项准入→人工采纳入库')
  page.reload(wait_until='networkidle');assert client.get('/api/studio/summary').json()['approved']==1;checks.append('刷新后审核与入库状态持久保存')
  page.get_by_role('button',name='组卷与导出',exact=True).click();page.get_by_role('button',name='按规则组卷',exact=True).click();page.get_by_role('button',name='保存整卷快照',exact=True).wait_for();page.get_by_role('button',name='保存整卷快照',exact=True).click();page.get_by_role('button',name='导出试卷与解析 PDF',exact=True).wait_for();page.screenshot(path=str(out/'05_组卷与导出.png'),full_page=True);checks.append('原创来源规则组卷及不可变快照保存')
  page.get_by_role('button',name='导出试卷与解析 PDF',exact=True).click();page.wait_for_timeout(500)
  for _ in range(100):
   jobs=client.get('/api/jobs').json()
   if jobs and jobs[0]['state'] in ('done','failed','cancelled'):break
   time.sleep(.5)
  assert jobs[0]['state']=='done',jobs[0];checks.append('实际双份PDF完成，公式错误为零')
  paper=client.get('/api/papers/'+jobs[0]['paper_id']).json();files=[]
  for f in jobs[0]['files']:
   path=out/f['name'];path.write_bytes(client.get('/api/download/'+f['name']).content);files.append({'path':str(path),'pages':f['pages'],'kind':f['kind']})
  page.get_by_role('button',name='数据与设置',exact=True).click();page.get_by_role('button',name='创建备份',exact=True).click();page.get_by_role('status').filter(has_text='数据库一致性备份已保存').wait_for();page.screenshot(path=str(out/'06_数据与设置.png'),full_page=True);checks.append('真实界面数据库备份')
  page.set_viewport_size({'width':800,'height':900});page.get_by_role('button',name='总览',exact=True).click();page.screenshot(path=str(out/'07_小屏布局.png'),full_page=True)
  assert not errors,errors;assert page.locator('.math-error').count()==0
  (out/'验收结果.json').write_text(json.dumps({'passed':True,'checks':checks,'browser_errors':errors,'pdfs':files,'database_scope':'隔离测试数据；人工采纳记录为测试，不进入正式数据库','paper_id':paper['id']},ensure_ascii=False,indent=2),encoding='utf-8');browser.close()
  print(json.dumps({'passed':True,'checks':len(checks),'pdfs':files},ensure_ascii=False))
finally:server.terminate();server.wait(timeout=10);log.close()
