"""Build a self-contained Windows folder; snapshot current project DB for private trial."""
import os,sys,pathlib,subprocess,shutil,sqlite3,contextlib,json,datetime,re
root=pathlib.Path(__file__).resolve().parents[2];appdir=root/'应用';deliver=root/'交付';deliver.mkdir(exist_ok=True)
data_home=pathlib.Path(os.environ.get('MATH2_HOME',str(deliver/'Windows_v1.2.0_02'/'Math2Studio'))).resolve()
source_database=data_home/'用户数据'/'math2.sqlite3'
if not source_database.is_file():raise FileNotFoundError('当前题库不存在，请通过MATH2_HOME指定数据目录：'+str(source_database))
version=re.search(r"^VERSION='([^']+)'",(appdir/'backend'/'main.py').read_text(encoding='utf-8'),re.M).group(1)
n=1
while (deliver/f'Windows_v{version}_{n:02d}').exists():n+=1
target=deliver/f'Windows_v{version}_{n:02d}';target.mkdir();build=root/'构建'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S');build.mkdir(parents=True)
tmp=build/'temp';tmp.mkdir();env=os.environ.copy();env.update(TEMP=str(tmp),TMP=str(tmp),PYINSTALLER_CONFIG_DIR=str(build/'cache'),PYTHONIOENCODING='utf-8')
args=[sys.executable,'-m','PyInstaller','--name','Math2Studio','--onedir','--console','--distpath',str(target),'--workpath',str(build/'work'),'--specpath',str(build),'--paths',str(appdir),'--add-data',str(appdir/'assets')+';assets','--add-data',str(appdir/'frontend'/'dist')+';frontend/dist','--collect-all','playwright','--collect-submodules','uvicorn','--hidden-import','backend.main','--hidden-import','backend.studio','--hidden-import','backend.model','--hidden-import','backend.auto_review',str(appdir/'launcher.py')]
subprocess.run(args,cwd=appdir,env=env,check=True)
package=target/'Math2Studio';browser=package/'浏览器'
for name in ('chromium_headless_shell-1169','ffmpeg-1011','winldd-1007'):
 shutil.copytree(root/'开发依赖'/'浏览器'/name,browser/name)
(package/'用户数据').mkdir(exist_ok=True)
with contextlib.closing(sqlite3.connect(source_database.as_uri()+'?mode=ro',uri=True)) as src,contextlib.closing(sqlite3.connect(package/'用户数据'/'math2.sqlite3')) as dst:src.backup(dst)
manifest={'version':version,'created':datetime.datetime.now().isoformat(),'package':str(package),'private_project_data':True,'contains_credentials':False,'browser':'Playwright Chromium 1169','instruction':'双击Math2Studio.exe，浏览器自动打开本机页面。此私人试用包含你的题库副本，公开分发前需换为无第三方正文的数据包。'}
(target/'交付清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(package/'先读我.txt').write_text(f'数学二智能命题与审卷系统 v{version}\n\n双击 Math2Studio.exe。浏览器自动打开；关闭运行窗口停止服务。\n包含本项目题库的数据库副本，原始PDF与Excel没有改动。\n用户数据、备份、导出均保存在当前目录，可整体迁移。\n模型API未配置，配置API后，生成或导入候选会自动重解、审题、修改复核并入库，不要求人工确认；未知题自动搁置。\n本包含私人题库资料，请勿未经授权公开分发；软件代码和第三方题库权利须分别核对。\nWindows未签名应用可能有系统提示。本机测试不能替代其他Windows版本兼容性测试。\n',encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False))
