"""Actual frontend layout audit; source application or the final standalone EXE.

No synthetic questions are written into the real bank. A read-only Playwright
route supplies existing questions to the real print component for bulk rendering.
"""
import argparse,contextlib,copy,json,os,pathlib,sqlite3,subprocess,sys,time
import httpx
from playwright.sync_api import sync_playwright
from pypdf import PdfReader

args=argparse.ArgumentParser();args.add_argument('--package',action='store_true');options=args.parse_args()
root=pathlib.Path(__file__).resolve().parents[2];out=root/'验收记录'/'公式排版界面';out.mkdir(exist_ok=True)
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
if options.package:
    package=pathlib.Path(json.loads((root/'验收记录/最新Windows交付.json').read_text(encoding='utf-8'))['package'])
    home=out/('交付隔离_'+time.strftime('%H%M%S'));(home/'用户数据').mkdir(parents=True)
    with contextlib.closing(sqlite3.connect(package/'用户数据/math2.sqlite3')) as src,contextlib.closing(sqlite3.connect(home/'用户数据/math2.sqlite3')) as dst:src.backup(dst)
    env.update(MATH2_HOME=str(home),MATH2_NO_BROWSER='1')
    os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(package/'浏览器')
    command=[str(package/'Math2Studio.exe')];cwd=package
else:
    home=root;env['MATH2_HOME']=str(root)
    env['PLAYWRIGHT_BROWSERS_PATH']=str(root/'开发依赖/浏览器');os.environ['PLAYWRIGHT_BROWSERS_PATH']=env['PLAYWRIGHT_BROWSERS_PATH']
    command=[sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8818'];cwd=root/'应用'
log=(out/('交付服务日志.txt' if options.package else '源码服务日志.txt')).open('w',encoding='utf-8')
server=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=log)
base=None
try:
    for _ in range(100):
        for port in (range(8765,8795) if options.package else [8818]):
            try:
                candidate=f'http://127.0.0.1:{port}'
                if httpx.get(candidate+'/api/health',timeout=.15).json()['version']=='1.2.0':base=candidate;break
            except (httpx.HTTPError,ValueError,KeyError):pass
        if base:break
        if server.poll() is not None:raise RuntimeError('服务启动失败，请检查日志')
        time.sleep(.2)
    assert base,'服务未就绪'
    client=httpx.Client(base_url=base,timeout=30)
    dashboard=client.get('/api/dashboard').json();assert dashboard['questions']==1244 and dashboard['eligible']==269,dashboard
    for qid in ('EXAM-M2-2026-04','EXAM-M2-2022-06','LL27-M2-C04-JC-X-009'):
        q=client.get('/api/questions/'+qid).json();assert q['eligible'] and q['presentation_source_check']
    with contextlib.closing(sqlite3.connect(home/'用户数据/math2.sqlite3')) as c:
        qs=[json.loads(r[0]) for r in c.execute('SELECT r.payload FROM questions q JOIN revisions r ON r.rev=q.current_rev')]
    ready=[q for q in qs if q['eligible']];errors=[]
    selected=['EXAM-M2-2026-04','EXAM-M2-2022-06','LL27-M2-C02-JC-X-015','LL27-M2-C04-JC-X-001','LL27-M2-C04-JC-X-009','LL27-M2-C07-JC-X-001','LL27-M2-C12-JC-X-001','LL27-M2-C05-JC-X-004']
    sample=[next(q for q in ready if q['id']==qid) for qid in selected]
    current={'rows':ready}
    def intercept(route):
        items=[{'number':i,'points':q['original_points'],'question':q} for i,q in enumerate(current['rows'],1)]
        p={'id':'P-LAYOUT-AUDIT','title':'已有题目排版验收（非新试卷）','mode':'chapter','items':items,'minutes':None}
        route.fulfill(status=200,json=p)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1100,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base,wait_until='networkidle')
        page.get_by_role('button',name='素材库',exact=True).click()
        page.get_by_label('核验筛选').select_option('eligible')
        page.get_by_label('来源筛选').select_option('880')
        page.get_by_text('共 59 条 · 已选 0 题',exact=True).wait_for()
        assert not page.locator('.math-error').count(),'素材预览发生公式截断'
        page.screenshot(path=str(out/'880素材库.png'),full_page=True)
        page.route('**/api/papers/P-LAYOUT-AUDIT?*',intercept)
        page.goto(base+'/?print=P-LAYOUT-AUDIT&kind=answers',wait_until='networkidle');page.wait_for_function('window.printReady === true')
        bulk_errors=page.locator('.math-error').all_text_contents();assert not bulk_errors,bulk_errors[:5]
        formulas=page.locator('.formula').count();assert formulas>4000,formulas
        assert page.locator('.print-question').count()==269
        current['rows']=sample
        page.goto(base+'/?print=P-LAYOUT-AUDIT&kind=exam',wait_until='networkidle');page.wait_for_function('window.printReady === true')
        assert not page.locator('.math-error').count()
        assert page.locator('.katex').count()>35
        for index,it in enumerate(page.locator('.print-question').all(),1):
            if index in (1,2,3,4,5,6,7,8):it.screenshot(path=str(out/f'题面_{index:02d}.png'))
        pdf=out/('交付版_排版验收.pdf' if options.package else '源码版_排版验收.pdf')
        page.pdf(path=str(pdf),format='A4',margin={'top':'18mm','bottom':'18mm','left':'18mm','right':'18mm'},print_background=True)
        count=len(PdfReader(pdf).pages);assert count>=2
        # A deliberately unwrapped integral must be visibly rejected by the
        # frontend, which is the same error channel the PDF exporter checks.
        current['rows']=[dict(sample[0],stem='测试未定界公式：∫_0^1 x² dx。')]
        page.goto(base+'/?print=P-LAYOUT-AUDIT&kind=exam',wait_until='networkidle');page.wait_for_function('window.printReady === true')
        assert page.locator('.math-error').count()>0
        browser.close()
    assert not errors,errors
    evidence={'passed':True,'version':'1.2.0','standalone':options.package,'questions':269,'sources':{'历年真题':188,'880':59,'项目原创示例':22},'rendered_formulas':formulas,'math_errors':bulk_errors,'pdf':str(pdf),'pdf_pages':count,'checks':['269道可用题由真实前端全量渲染','原页修正题通过真实API读取','8个代表题截图及真实Chromium PDF导出','未定界积分被错误通道拦截','本次未新增题目或试卷到真实题库'],'limits':['全量渲染无报错不等于全量原页逐字核对','旧转写中简写、遗漏条件及数学正确性仍按既有核验状态处理']}
    (out/('交付版验收.json' if options.package else '源码版验收.json')).write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=False))
finally:
    if server.poll() is None:server.terminate();server.wait(timeout=15)
    log.close()
