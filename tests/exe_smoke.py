"""Verify the distributed EXE in a directory without source files or Python."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import psutil

from tests.helpers import cleanup_child, listening_child
from tests.windows import close, minimize, screenshot, startup_error, user32, wait_until, window_for_pid


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, default=root / 'dist' / 'Portside.exe')
    args = parser.parse_args()
    report = {}
    (root / '.runtime').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='独立运行-', dir=root / '.runtime') as temporary:
        directory = Path(temporary)
        executable = directory / 'Portside.exe'
        shutil.copy2(args.exe, executable)
        profile = directory / '用户配置'
        runtime = profile / 'Portside' / 'runtime'
        environment = os.environ.copy()
        environment['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        environment.pop('PYTHONPATH', None)
        environment.pop('PYTHONHOME', None)
        environment['LOCALAPPDATA'] = str(profile)
        with socket.socket() as debug_socket:
            debug_socket.bind(('127.0.0.1', 0))
            debug_port = debug_socket.getsockname()[1]
        # Enabled only for this test process, never for ordinary EXE launches.
        environment['QTWEBENGINE_REMOTE_DEBUGGING'] = f'127.0.0.1:{debug_port}'
        launcher = subprocess.Popen(
            [str(executable)],
            cwd=directory, env=environment, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        child = None
        instance = None
        all_launchers = [launcher]
        try:
            deadline = time.monotonic() + 90
            record = None
            while time.monotonic() < deadline:
                records = list(runtime.glob('*.json')) if runtime.exists() else []
                if records:
                    record = json.loads(records[0].read_text(encoding='utf-8'))
                    break
                if launcher.poll() is not None:
                    raise AssertionError(f'EXE exited before startup: {launcher.returncode}')
                time.sleep(.1)
            assert record, 'EXE did not publish a runtime record'
            instance = psutil.Process(record['pid'])
            assert abs(instance.create_time() - record['create_time']) < .001
            assert Path(instance.exe()).resolve() == executable.resolve()
            def shown_window(pid):
                error = startup_error(pid)
                assert not error, error
                return window_for_pid(pid)

            hwnd = wait_until(lambda: shown_window(record['pid']), 'EXE did not show a standalone window')
            user32.SetWindowTextW(hwnd, 'Portside · 进程与端口工作台（自动验证）')
            origin = record['origin']
            probe = subprocess.run([shutil.which('node'), str(root / 'tests' / 'desktop_probe.mjs'),
                                    f'http://127.0.0.1:{debug_port}', origin],
                                   capture_output=True, text=True, encoding='utf-8', timeout=60)
            assert probe.returncode == 0, probe.stderr or probe.stdout
            html = urllib.request.urlopen(origin, timeout=20).read().decode('utf-8')
            token = re.search(r'name="panel-token" content="([^"]+)"', html)[1]
            assert '本机进程控制台' in html

            def request(path, body=None):
                headers = {'X-Panel-Token': token}
                if body is not None:
                    headers.update({'Content-Type': 'application/json', 'Origin': origin})
                req = urllib.request.Request(origin + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as response:
                    return json.loads(response.read())

            for asset in ('styles.css', 'app.js', 'model.mjs', 'favicon.svg'):
                with urllib.request.urlopen(f'{origin}/static/{asset}', timeout=10) as response:
                    assert response.status == 200 and response.read(), f'Bundled asset missing: {asset}'
            deadline = time.monotonic() + 20
            snapshot = request('/api/snapshot')
            while (not snapshot['ready'] or not any(p['pid'] == record['pid'] for p in snapshot['processes'])) and time.monotonic() < deadline:
                time.sleep(.1)
                snapshot = request('/api/refresh', {})
            assert snapshot['ready'], 'EXE never produced a system snapshot'
            (root / '.runtime' / 'exe-startup-snapshot.json').write_text(json.dumps({
                'record': record, 'processes': snapshot['processes'], 'warnings': snapshot['warnings']
            }, ensure_ascii=False, indent=2), encoding='utf-8')
            assert any(p['pid'] == record['pid'] for p in snapshot['processes']), (
                f"Own PID {record['pid']} missing from {len(snapshot['processes'])} processes: "
                f"{[(p['pid'], p['name']) for p in snapshot['processes'] if 'portside' in p['name'].lower()]}")
            try:
                urllib.request.urlopen(origin + '/api/snapshot', timeout=10)
                raise AssertionError('API accepted missing token')
            except urllib.error.HTTPError as error:
                assert error.code == 403

            minimize(hwnd)
            # Window activation must work even when the diagnostic record is missing.
            record_path = runtime / f"{record['pid']}.json"
            record_path.unlink()
            duplicate = subprocess.Popen(
                [str(executable)],
                cwd=directory, env=environment, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            all_launchers.append(duplicate)
            try:
                assert duplicate.wait(timeout=60) == 0, 'Duplicate launch did not reuse the existing instance'
            finally:
                if duplicate.poll() is None:
                    duplicate.kill()
                    duplicate.wait(timeout=10)
            wait_until(lambda: not user32.IsIconic(hwnd), 'Duplicate launch did not restore the window')
            assert not list(runtime.glob('*.json')), 'Duplicate launch created a second instance'
            record_path.write_text(json.dumps(record), encoding='utf-8')
            child, ports = listening_child()
            created = psutil.Process(child.pid).create_time()
            snapshot = request('/api/refresh', {})
            def live_renderers():
                assert instance.is_running() and window_for_pid(instance.pid), 'Test window was closed during verification'
                workers = []
                for process in instance.children(recursive=True):
                    try:
                        if process.name().lower() == 'qtwebengineprocess.exe' and '--type=renderer' in process.cmdline():
                            workers.append(process)
                    except psutil.NoSuchProcess:
                        pass
                return workers

            renderers = wait_until(live_renderers, 'EXE did not start its page renderer', timeout=30)
            # Renderer workers can start after the cached process sample. Verify
            # protection against each live identity through the authoritative API.
            for renderer in renderers:
                detail = request(f'/api/processes/{renderer.pid}')
                assert detail['protected_reason'], f'Desktop renderer was not protected: {detail}'
            assert any(c['pid'] == child.pid and c['port'] == ports['tcp'] for c in snapshot['connections'])
            assert any(c['pid'] == child.pid and c['port'] == ports['udp'] for c in snapshot['connections'])
            try:
                request(f"/api/processes/{record['pid']}/terminate", {'create_time': record['create_time']})
                raise AssertionError('EXE did not protect itself')
            except urllib.error.HTTPError as error:
                assert error.code == 403
            result = request(f'/api/processes/{child.pid}/terminate', {'create_time': created})
            assert result['terminated']
            child.wait(timeout=10)
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', ports['tcp']))
            assert instance.is_running(), 'Interactive EXE exited unexpectedly'
            # Allow the rendered UI to finish its next automatic refresh before capture.
            time.sleep(2.2)
            screenshot(hwnd, root / '.runtime' / 'exe-desktop-preview.png')
            descendants = instance.children(recursive=True)
            close(hwnd)
            instance.wait(timeout=30)
            assert launcher.wait(timeout=30) == 0, 'Window close did not exit cleanly'
            assert not record_path.exists(), 'Window close left a runtime record'
            _, alive = psutil.wait_procs(descendants, timeout=15)
            assert not alive, 'Window close left Qt rendering processes running'
            assert not any(connection.pid == record['pid'] and connection.status == 'LISTEN'
                           for connection in psutil.net_connections(kind='tcp')), 'Closed EXE left a listening socket'

            # Race two ordinary launches after close; one must own the window.
            pair = [subprocess.Popen([str(executable)], cwd=directory, env=environment,
                                     creationflags=subprocess.CREATE_NO_WINDOW) for _ in range(2)]
            all_launchers.extend(pair)
            new_path = wait_until(lambda: next(iter(runtime.glob('*.json')), None),
                                  'EXE did not restart after window close', timeout=90)
            fresh = json.loads(new_path.read_text(encoding='utf-8'))
            instance = psutil.Process(fresh['pid'])
            fresh_window = wait_until(lambda: shown_window(instance.pid), 'Relaunch did not show a window')
            user32.SetWindowTextW(fresh_window, 'Portside · 进程与端口工作台（自动验证）')
            parent = instance.ppid()
            secondary = next(p for p in pair if p.pid != parent)
            assert secondary.wait(timeout=60) == 0, 'Simultaneous launch did not reuse the first window'
            assert len(list(runtime.glob('*.json'))) == 1, 'Simultaneous launch created multiple instances'
            close(fresh_window)
            instance.wait(timeout=30)
            for process in pair:
                assert process.wait(timeout=30) == 0
            assert not list(runtime.glob('*.json'))
            report = {
                'standalone_exe': True, 'unicode_path': True, 'python_removed_from_path': True,
                'bundled_assets': True, 'standalone_native_window': True, 'default_runtime_path': True,
                'duplicate_instance_reused': True, 'minimized_window_restored': True,
                'missing_record_activation': True, 'simultaneous_launches': True,
                'close_exits_and_releases_port': True, 'qt_children_exit': True, 'relaunch_after_close': True,
                'real_processes': len(snapshot['processes']), 'tcp_udp_ownership': True,
                'self_protection': True, 'process_termination': True, 'port_released': True,
                'renderer_protection': True,
                'live_dashboard_rendered': True, 'packaged_fuzzy_search': True,
                'exe_bytes': executable.stat().st_size,
            }
        finally:
            if child:
                cleanup_child(child)
            # Only clean the processes started by this test, including renderer children.
            for process in all_launchers:
                if process.poll() is None:
                    try:
                        parent = psutil.Process(process.pid)
                        descendants = parent.children(recursive=True)
                        for descendant in reversed(descendants):
                            try:
                                descendant.terminate()
                            except psutil.NoSuchProcess:
                                pass
                        parent.terminate()
                        psutil.wait_procs([parent, *descendants], timeout=15)
                    except psutil.NoSuchProcess:
                        pass
                    process.wait(timeout=15)
    (root / '.runtime' / 'exe-smoke-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
