import http.client
import json
import os
import threading
import unittest

import psutil

from panel.monitor import Monitor
from panel.server import PanelServer
from tests.helpers import cleanup_child, listening_child


class ServerTests(unittest.TestCase):
    def test_another_instance_cannot_listen_on_the_same_endpoint(self):
        first = PanelServer()
        self.addCleanup(first.server_close)
        try:
            second = PanelServer(port=first.server_address[1])
        except OSError:
            return
        second.server_close()
        self.fail('Two independent panels bound the same endpoint')

    @classmethod
    def setUpClass(cls):
        cls.monitor = Monitor()
        cls.monitor.refresh()
        cls.server = PanelServer(port=0, monitor=cls.monitor)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]
        cls.origin = f'http://127.0.0.1:{cls.port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.monitor.close()

    def request(self, method, path, body=None, headers=None):
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=20)
        auth = {'X-Panel-Token': self.server.token}
        if body is not None:
            auth['Content-Type'] = 'application/json'
            body = json.dumps(body).encode() if not isinstance(body, bytes) else body
        auth.update(headers or {})
        try:
            client.request(method, path, body=body, headers=auth)
            response = client.getresponse()
            data = response.read()
            return response.status, data, dict(response.getheaders())
        finally:
            client.close()

    def test_index_serves_session_bootstrap_and_csp(self):
        status, data, headers = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(self.server.token.encode(), data)
        self.assertIn('Content-Security-Policy', headers)
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_missing_token_is_rejected(self):
        status, _, _ = self.request('GET', '/api/snapshot', headers={'X-Panel-Token': ''})
        self.assertEqual(status, 403)

    def test_foreign_origin_is_rejected_even_with_token(self):
        status, _, _ = self.request('POST', '/api/refresh', {}, {'Origin': 'https://example.com'})
        self.assertEqual(status, 403)

    def test_foreign_host_is_rejected(self):
        status, _, _ = self.request('GET', '/', headers={'Host': 'attacker.example'})
        self.assertEqual(status, 403)

    def test_cross_site_browser_request_is_rejected(self):
        status, _, _ = self.request('GET', '/', headers={'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(status, 403)

    def test_snapshot_returns_real_data(self):
        status, data, _ = self.request('GET', '/api/snapshot')
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)['ready'])
        self.assertTrue(any(p['pid'] == os.getpid() for p in json.loads(data)['processes']))

    def test_invalid_json_is_a_readable_error(self):
        status, data, _ = self.request('POST', f'/api/processes/{os.getpid()}/terminate', b'{')
        self.assertEqual(status, 400)
        self.assertIn('error', json.loads(data))

    def test_wrong_content_type_is_rejected(self):
        status, _, _ = self.request('POST', '/api/refresh', b'{}', {'Content-Type': 'text/plain'})
        self.assertEqual(status, 415)

    def test_json_array_is_rejected(self):
        status, _, _ = self.request('POST', '/api/refresh', [])
        self.assertEqual(status, 400)

    def test_static_path_traversal_is_not_served(self):
        status, _, _ = self.request('GET', '/static/../requirements.txt')
        self.assertEqual(status, 404)

    def test_oversized_request_is_rejected(self):
        status, _, _ = self.request('POST', '/api/refresh', b' ' * 9000)
        self.assertEqual(status, 413)

    def test_terminate_requires_current_identity_and_releases_port(self):
        child, ports = listening_child()
        self.addCleanup(cleanup_child, child)
        identity = psutil.Process(child.pid).create_time()
        status, _, _ = self.request('POST', f'/api/processes/{child.pid}/terminate', {'create_time': identity - 10})
        self.assertEqual(status, 409)
        self.assertIsNone(child.poll())
        status, data, _ = self.request('GET', f'/api/processes/{child.pid}')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)['create_time'], identity)
        status, data, _ = self.request('POST', f'/api/processes/{child.pid}/terminate', {'create_time': identity}, {'Origin': self.origin})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)['terminated'])
        child.wait(timeout=10)
        status, data, _ = self.request('GET', '/api/snapshot')
        self.assertFalse(any(c['pid'] == child.pid and c['port'] == ports['tcp'] for c in json.loads(data)['connections']))


if __name__ == '__main__':
    unittest.main()
