# -*- coding: utf-8 -*-
"""
本地静态服务器：禁止缓存（开发时修改代码立即生效），并强制正确的 MIME 类型
（Windows 注册表有时把 .js 映射成 text/plain，会导致 ES Module 加载失败）。

用法：python tools/devserver.py [端口，默认 5186]
"""
import http.server
import os
import sys
import socketserver

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5186

TYPES = {
    '.js': 'text/javascript; charset=utf-8',
    '.mjs': 'text/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.png': 'image/png',
    '.wav': 'audio/wav',
    '.ogg': 'audio/ogg',
    '.md': 'text/plain; charset=utf-8',
}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def guess_type(self, path):
        ext = os.path.splitext(path)[1].lower()
        return TYPES.get(ext) or super().guess_type(path)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, max-age=0')
        super().end_headers()

    def log_message(self, fmt, *args):
        if '404' in (fmt % args):
            sys.stderr.write('%s\n' % (fmt % args))


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == '__main__':
    with Server(('127.0.0.1', PORT), Handler) as httpd:
        print('灰烬王冠 已启动： http://localhost:%d/' % PORT)
        sys.stdout.flush()
        httpd.serve_forever()
