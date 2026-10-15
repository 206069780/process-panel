"""Verify the bulk Windows sampler against real process identities."""

import importlib.util
import os
import unittest
from unittest.mock import patch
import copy

import psutil


@unittest.skipUnless(os.name == 'nt', 'Windows sampler')
class WindowsSnapshotTests(unittest.TestCase):
    def test_bulk_snapshot_matches_this_process_identity(self):
        self.assertIsNotNone(importlib.util.find_spec('panel.win_snapshot'), 'Bulk sampler is missing')
        from panel.win_snapshot import query_processes
        rows = query_processes()
        current = psutil.Process()
        found = next(row for row in rows if row['pid'] == current.pid)
        self.assertEqual(found['name'].lower(), current.name().lower())
        self.assertAlmostEqual(found['create_time'], current.create_time(), delta=.001)
        self.assertGreater(found['memory'], 0)
        self.assertGreaterEqual(found['cpu_total'], 0)
        self.assertLessEqual(found['cpu_total'], sum(current.cpu_times()[:2]) + .1)
        self.assertEqual(len(rows), len({row['pid'] for row in rows}))

    def test_monitor_avoids_per_pid_fallback_scans(self):
        from panel.monitor import Monitor
        with patch('psutil.process_iter', side_effect=AssertionError('Per-PID fallback scan was used')):
            snapshot = Monitor().refresh()
        current = next(row for row in snapshot['processes'] if row['pid'] == os.getpid())
        self.assertGreater(current['memory'], 0)
        self.assertIsNotNone(current['protected_reason'])

    def test_cpu_deltas_are_normalized_and_pid_reuse_starts_at_zero(self):
        from panel.win_snapshot import WindowsProcessSampler
        def row(created, total):
            return {'pid': 123, 'name': 'sample.exe', 'create_time': created,
                    'memory': 4096, 'cpu_total': total}
        samples = [[row(1, 10)], [row(1, 12)], [row(2, 50)]]
        with patch('panel.win_snapshot.query_processes', side_effect=copy.deepcopy(samples)), \
                patch('panel.win_snapshot.time.monotonic', side_effect=[10, 12, 14]):
            sampler = WindowsProcessSampler()
            self.assertEqual(sampler.sample(2)[0]['cpu'], 0)
            self.assertEqual(sampler.sample(2)[0]['cpu'], 50)
            self.assertEqual(sampler.sample(2)[0]['cpu'], 0)
            self.assertNotIn((123, 1), sampler.previous)

    def test_invalid_name_pointer_is_rejected(self):
        import ctypes
        from panel.win_snapshot import ProcessInformation, _decode
        buffer = ctypes.create_string_buffer(ctypes.sizeof(ProcessInformation))
        entry = ProcessInformation.from_buffer(buffer)
        entry.ImageName.Length = 2
        entry.ImageName.MaximumLength = 2
        entry.ImageName.Buffer = 1
        with self.assertRaises(ValueError):
            _decode(buffer, len(buffer))

    def test_monitor_falls_back_when_native_query_is_unavailable(self):
        from panel.monitor import Monitor
        with patch('panel.win_snapshot.query_processes', side_effect=OSError('Unsupported API')):
            snapshot = Monitor().refresh()
        current = next(row for row in snapshot['processes'] if row['pid'] == os.getpid())
        self.assertAlmostEqual(current['create_time'], psutil.Process().create_time(), delta=.001)
        self.assertTrue(snapshot['ready'])


if __name__ == '__main__':
    unittest.main()
