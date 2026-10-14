"""Portable loopback launcher; no dependency on Codex or author-machine paths."""
import os,sys,pathlib,socket,webbrowser,threading,time
root=pathlib.Path(sys.executable).parent if getattr(sys,'frozen',False) else pathlib.Path(__file__).resolve().parent.parent
if not getattr(sys,'frozen',False):
 current_package=root/'交付'/'Windows_v1.2.0_02'/'Math2Studio'
 if (current_package/'用户数据'/'math2.sqlite3').is_file():root=current_package
os.environ.setdefault('MATH2_HOME',str(root))
local_browsers=root/'浏览器'
if not local_browsers.exists():local_browsers=root/'开发依赖'/'浏览器'
if local_browsers.exists():os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(local_browsers)
os.environ.setdefault('PYTHONIOENCODING','utf-8')
def main():
 import uvicorn
 for port in range(8765,8795):
  with socket.socket() as s:
   try:s.bind(('127.0.0.1',port));break
   except OSError:continue
 else:raise RuntimeError('本机端口8765—8794均被占用')
 url=f'http://127.0.0.1:{port}'
 if '--no-browser' not in sys.argv:
  def open_browser():
   for _ in range(100):
    time.sleep(.2)
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2):webbrowser.open(url);return
    except OSError:pass
  threading.Thread(target=open_browser,daemon=True).start()
 print('数学二命题工作室：'+url+'；关闭此运行窗口停止服务。')
 uvicorn.run('backend.main:app',host='127.0.0.1',port=port,log_level='warning')
if __name__=='__main__':main()
