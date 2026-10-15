import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import os
import subprocess
import sys

from panel.desktop import InstanceLock, RuntimeRegistry
from panel.tray import launch_admin


class RuntimeRegistryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.registry = RuntimeRegistry(self.root)

    def test_no_instance_is_found_in_empty_directory(self):
        self.assertIsNone(self.registry.find_existing())

    def test_invalid_json_is_ignored(self):
        (self.root / 'broken.json').write_text('{', encoding='utf-8')
        self.assertIsNone(self.registry.find_existing())

    def test_unrelated_python_process_cannot_be_reused(self):
        self.registry.register('http://127.0.0.1:12345', False)
        self.assertIsNone(self.registry.find_existing())

    def test_only_own_runtime_record_is_removed(self):
        other = self.root / 'other.json'
        other.write_text('{}', encoding='utf-8')
        self.registry.register('http://127.0.0.1:12345', False)
        self.registry.unregister()
        self.assertTrue(other.exists())
        self.assertEqual(list(self.root.glob('*.json')), [other])

    def test_registry_records_actual_pid_and_creation_time(self):
        import os
        import psutil
        self.registry.register('http://127.0.0.1:12345', False)
        record = json.loads((self.root / f'{os.getpid()}.json').read_text(encoding='utf-8'))
        self.assertEqual(record['pid'], os.getpid())
        self.assertEqual(record['create_time'], psutil.Process().create_time())

    def test_elevated_launch_resets_frozen_environment_and_restores_parent(self):
        import os
        with patch.dict(os.environ, {'PYINSTALLER_RESET_ENVIRONMENT': 'original'}):
            with patch('panel.tray.ctypes.windll.shell32.ShellExecuteW') as launch:
                def capture(*args):
                    self.assertEqual(os.environ['PYINSTALLER_RESET_ENVIRONMENT'], '1')
                    return 42
                launch.side_effect = capture
                self.assertTrue(launch_admin())
            self.assertEqual(os.environ['PYINSTALLER_RESET_ENVIRONMENT'], 'original')

    def test_elevation_cancel_is_reported_and_environment_cleaned(self):
        import os
        with patch.dict(os.environ, {}, clear=True):
            with patch('panel.tray.ctypes.windll.shell32.ShellExecuteW', return_value=5):
                self.assertFalse(launch_admin())
            self.assertNotIn('PYINSTALLER_RESET_ENVIRONMENT', os.environ)


@unittest.skipUnless(os.name == 'nt', 'Windows mutex lifecycle')
class InstanceLockTests(unittest.TestCase):
    def test_lock_scope_includes_runtime_directory(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            with InstanceLock(False, first) as a, InstanceLock(False, second) as b:
                self.assertNotEqual(a.name, b.name)
                self.assertTrue(a.primary)
                self.assertTrue(b.primary)

    def test_abrupt_exit_releases_ownership_even_if_secondary_keeps_handle(self):
        import psutil
        script = f'import sys; sys.path[:] = {sys.path!r}; sys.executable = {sys.executable!r}\n' + '''
import sys
from panel.desktop import InstanceLock
lock = InstanceLock(False, sys.argv[1])
print(lock.primary, flush=True)
sys.stdin.readline()
'''
        with tempfile.TemporaryDirectory() as directory:
            owner = subprocess.Popen([sys._base_executable, '-u', '-c', script, directory],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(owner.stdout.readline().strip(), 'True')
                with InstanceLock(False, directory) as secondary:
                    self.assertFalse(secondary.primary)
                    psutil.Process(owner.pid).kill()
                    owner.wait(timeout=10)
                    with InstanceLock(False, directory) as replacement:
                        self.assertTrue(replacement.primary)
            finally:
                if owner.poll() is None:
                    owner.kill()
                    owner.wait(timeout=10)
                owner.stdin.close()
                owner.stdout.close()


if __name__ == '__main__':
    unittest.main()
