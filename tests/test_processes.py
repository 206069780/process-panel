import os
import socket
import unittest

import psutil

from panel.monitor import Monitor
from panel.processes import PanelError, process_detail, terminate_process
from tests.helpers import cleanup_child, listening_child


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.child, self.ports = listening_child()
        self.addCleanup(cleanup_child, self.child)
        self.created = psutil.Process(self.child.pid).create_time()

    def test_snapshot_finds_real_tcp_and_udp_owners(self):
        snapshot = Monitor().refresh()
        owned = [p for p in snapshot['connections'] if p['pid'] == self.child.pid]
        self.assertTrue(any(p['protocol'] == 'TCP' and p['port'] == self.ports['tcp']
                            and p['state'] == 'LISTEN' for p in owned))
        self.assertTrue(any(p['protocol'] == 'UDP' and p['port'] == self.ports['udp']
                            for p in owned))
        process = next(p for p in snapshot['processes'] if p['pid'] == self.child.pid)
        self.assertIn(self.ports['tcp'], process['ports'])
        self.assertGreater(snapshot['system']['memory_total'], 0)
        self.assertGreater(snapshot['system']['process_count'], 0)

    def test_detail_has_actual_process_identity(self):
        detail = process_detail(self.child.pid)
        self.assertEqual(detail['pid'], self.child.pid)
        self.assertEqual(detail['create_time'], self.created)
        self.assertTrue(detail['exe'].lower().endswith('python.exe') or 'python' in detail['exe'])
        self.assertIsNone(detail['protected_reason'])

    def test_stale_identity_is_rejected_without_ending_process(self):
        with self.assertRaises(PanelError) as error:
            terminate_process(self.child.pid, self.created - 10)
        self.assertEqual(error.exception.status, 409)
        self.assertIsNone(self.child.poll())

    def test_own_process_is_protected(self):
        with self.assertRaises(PanelError) as error:
            terminate_process(os.getpid(), psutil.Process().create_time())
        self.assertEqual(error.exception.status, 403)

    def test_pid_zero_is_protected(self):
        with self.assertRaises(PanelError) as error:
            terminate_process(0, 0)
        self.assertEqual(error.exception.status, 403)

    def test_invalid_creation_times_are_rejected(self):
        for value in [None, True, '123', float('nan'), float('inf'), -1]:
            with self.subTest(value=value), self.assertRaises(PanelError) as error:
                terminate_process(self.child.pid, value)
            self.assertEqual(error.exception.status, 400)
        self.assertIsNone(self.child.poll())

    def test_termination_releases_the_tcp_port(self):
        result = terminate_process(self.child.pid, self.created)
        self.child.wait(timeout=10)
        self.assertEqual(result['pid'], self.child.pid)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', self.ports['tcp']))


if __name__ == '__main__':
    unittest.main()
