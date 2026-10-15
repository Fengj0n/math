"""Launch the isolated, offline PDF intake service."""
import argparse
import json
import logging
import sys
import threading
import urllib.request
import webbrowser

from .config import DATA, configure_environment


def main():
    parser = argparse.ArgumentParser(description='本地PDF题目导入，独立试用')
    parser.add_argument('--port', type=int, default=18326)
    parser.add_argument('--open', action='store_true', help='打开浏览器')
    args = parser.parse_args()
    url = f'http://127.0.0.1:{args.port}'
    # Check an existing local instance before installing the process-local offline guard.
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + '/api/health', timeout=2) as response:
            existing = json.load(response)
        if existing.get('app') == 'math2-local-pdf-import':
            if args.open:
                webbrowser.open(url)
            return
        raise RuntimeError('此端口已由其他程序使用，请使用 --port 指定其他端口。')
    except (OSError, urllib.error.URLError):
        pass
    configure_environment()
    DATA.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None or sys.stderr is None:
        stream = (DATA / '后台输出.txt').open('a', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = stream
    logging.basicConfig(filename=str(DATA / '运行日志.txt'), level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s %(message)s', encoding='utf-8')
    from .privacy import disable_outbound_connections
    disable_outbound_connections()
    from .service import create_app
    import uvicorn
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=args.port, log_config=None))
    app.state.shutdown = lambda: setattr(server, 'should_exit', True)
    if args.open:
        threading.Timer(2, lambda: webbrowser.open(url)).start()
    server.run()


if __name__ == '__main__':
    main()
