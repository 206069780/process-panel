"""Loopback-only HTTP boundary, explicit assets and authenticated JSON routes."""

import json
import os
from pathlib import Path
import re
import secrets
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .monitor import Monitor
from .processes import PanelError, process_detail, terminate_process

_STATIC = Path(__file__).resolve().parent.parent / 'static'
_ASSETS = {
    '/static/styles.css': ('styles.css', 'text/css; charset=utf-8'),
    '/static/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/static/model.mjs': ('model.mjs', 'text/javascript; charset=utf-8'),
    '/static/favicon.svg': ('favicon.svg', 'image/svg+xml'),
}


class PanelServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR permits unrelated listeners on the same port.
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, port=0, monitor=None):
        self.monitor = monitor if monitor is not None else Monitor()
        self.token = secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1', port), PanelHandler)
        self.origin = f'http://127.0.0.1:{self.server_address[1]}'


class PanelHandler(BaseHTTPRequestHandler):
    server_version = 'ProcessPanel/1.0'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format, *args):
        # Local command lines and process metadata do not belong in request logs.
        pass

    def _send(self, status, data, content_type='application/json; charset=utf-8'):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                         "base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _validate(self, api=False):
        if self.headers.get('Host') != self.server.origin.removeprefix('http://'):
            raise PanelError(403, '仅允许通过本机地址访问面板')
        origin = self.headers.get('Origin')
        if origin and origin != self.server.origin:
            raise PanelError(403, '请求来源不匹配，请从本机面板操作')
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise PanelError(403, '不允许其他网站访问本机面板')
        if api and not secrets.compare_digest(self.headers.get('X-Panel-Token', ''), self.server.token):
            raise PanelError(403, '面板会话已失效，请重新加载页面')

    def _json_body(self):
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            raise PanelError(415, '请求内容必须是 JSON')
        lengths = self.headers.get_all('Content-Length') or []
        if len(lengths) != 1 or self.headers.get('Transfer-Encoding'):
            raise PanelError(400, '无效的请求长度')
        try:
            length = int(lengths[0])
        except ValueError:
            raise PanelError(400, '无效的请求长度') from None
        if length < 0 or length > 8192:
            raise PanelError(413, '请求内容超过允许大小')
        try:
            def invalid_constant(value):
                raise ValueError(value)
            data = json.loads(self.rfile.read(length), parse_constant=invalid_constant)
        except (ValueError, UnicodeError):
            raise PanelError(400, 'JSON 格式无效') from None
        if not isinstance(data, dict):
            raise PanelError(400, '请求内容必须是 JSON 对象')
        return data

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            self._validate(api=path.startswith('/api/'))
            if path == '/':
                page = (_STATIC / 'index.html').read_text(encoding='utf-8')
                self._send(200, page.replace('__PANEL_TOKEN__', self.server.token).encode(), 'text/html; charset=utf-8')
            elif path in _ASSETS:
                filename, content_type = _ASSETS[path]
                self._send(200, (_STATIC / filename).read_bytes(), content_type)
            elif path == '/api/snapshot':
                self._send(200, self.server.monitor.snapshot())
            elif match := re.fullmatch(r'/api/processes/(\d+)', path):
                detail = process_detail(int(match[1]))
                detail['connections'] = [c for c in self.server.monitor.snapshot()['connections']
                                         if c['pid'] == detail['pid'] and c['create_time'] == detail['create_time']]
                self._send(200, detail)
            else:
                raise PanelError(404, '请求的页面或接口不存在')
        except PanelError as error:
            self._send(error.status, {'error': str(error)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self._send(500, {'error': '读取数据失败，请刷新后重试'})

    def do_POST(self):
        try:
            self._validate(api=True)
            path = urlsplit(self.path).path
            body = self._json_body()
            if path == '/api/refresh':
                self._send(200, self.server.monitor.refresh())
            elif match := re.fullmatch(r'/api/processes/(\d+)/terminate', path):
                result = terminate_process(int(match[1]), body.get('create_time'))
                self.server.monitor.refresh()
                self._send(200, result)
            else:
                raise PanelError(404, '请求的接口不存在')
        except PanelError as error:
            self._send(error.status, {'error': str(error)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self._send(500, {'error': '操作失败，请刷新后重试'})
