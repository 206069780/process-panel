"""Measure actual EXE window and live-page startup, with an optional local budget."""

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import tempfile
import time

import psutil

from tests.windows import close, startup_error, user32, wait_until, window_for_pid


def measure(executable, root, run):
    with tempfile.TemporaryDirectory(prefix='startup-', dir=root / '.runtime') as temporary:
        runtime = Path(temporary)
        with socket.socket() as candidate:
            candidate.bind(('127.0.0.1', 0))
            debug_port = candidate.getsockname()[1]
        environment = os.environ.copy()
        environment['QTWEBENGINE_REMOTE_DEBUGGING'] = f'127.0.0.1:{debug_port}'
        started = time.perf_counter()
        launcher = subprocess.Popen(
            [str(executable), '--port', '0', '--runtime-dir', str(runtime)],
            env=environment, cwd=executable.parent,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        parent = psutil.Process(launcher.pid)
        record = None
        hwnd = None
        timing = {'run': run}
        observed_workers = set()
        try:
            while time.perf_counter() - started < 90:
                assert launcher.poll() is None, f'Application exited: {launcher.returncode}'
                children = parent.children(recursive=True)
                observed_workers.update(children)
                if children and 'child_started' not in timing:
                    timing['child_started'] = round(time.perf_counter() - started, 3)
                if record is None:
                    for path in runtime.glob('*.json'):
                        try:
                            record = json.loads(path.read_text(encoding='utf-8'))
                        except (ValueError, OSError):
                            continue
                        timing['runtime_ready'] = round(time.perf_counter() - started, 3)
                        break
                if record:
                    error = startup_error(record['pid'])
                    assert not error, error
                    splash = window_for_pid(record['pid'], 'Portside · 正在启动')
                    if splash and 'animation_visible' not in timing:
                        timing['animation_visible'] = round(time.perf_counter() - started, 3)
                    hwnd = window_for_pid(record['pid'])
                    if hwnd:
                        timing['window_visible'] = round(time.perf_counter() - started, 3)
                        user32.SetWindowTextW(hwnd, 'Portside · 进程与端口工作台（自动验证，请勿关闭）')
                        break
                time.sleep(.025)
            assert hwnd, 'Application did not show its window'
            wait_until(lambda: not window_for_pid(record['pid'], 'Portside · 正在启动'),
                       'Startup animation did not close', timeout=5)
            probe = subprocess.run(
                [shutil.which('node'), str(root / 'tests' / 'desktop_probe.mjs'),
                 f'http://127.0.0.1:{debug_port}', record['origin']],
                capture_output=True, text=True, encoding='utf-8', timeout=65,
            )
            assert probe.returncode == 0, probe.stderr or probe.stdout
            timing['live_dashboard_ready'] = round(time.perf_counter() - started, 3)
            descendants = parent.children(recursive=True)
            observed_workers.update(descendants)
            close(hwnd)
            assert launcher.wait(timeout=45) == 0
            _, alive = psutil.wait_procs(descendants, timeout=15)
            assert not alive, 'Verification left application workers running'
            return timing
        finally:
            try:
                observed_workers.update(parent.children(recursive=True))
            except psutil.NoSuchProcess:
                pass
            # A launcher may already have exited while workers are still alive.
            # Process objects retain creation-time identity to avoid PID reuse.
            for child in observed_workers:
                try:
                    if child.is_running():
                        child.terminate()
                except psutil.NoSuchProcess:
                    pass
            if launcher.poll() is None:
                parent.terminate()
                launcher.wait(timeout=20)
            psutil.wait_procs(list(observed_workers), timeout=15)


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, default=root / 'dist' / 'Portside' / 'Portside.exe')
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--max-ready-seconds', type=float)
    parser.add_argument('--output', type=Path, default=root / '.runtime' / 'startup-benchmark.json')
    options = parser.parse_args()
    if options.runs < 1:
        parser.error('--runs must be positive')
    if not options.exe.is_file():
        parser.error(f'EXE not found: {options.exe}')
    (root / '.runtime').mkdir(exist_ok=True)
    results = []
    for run in range(1, options.runs + 1):
        timing = measure(options.exe.resolve(), root, run)
        print(json.dumps(timing), flush=True)
        results.append(timing)
    median = statistics.median(row['live_dashboard_ready'] for row in results)
    report = {'exe': str(options.exe.resolve()), 'runs': results,
              'median_ready_seconds': median,
              'median_window_seconds': statistics.median(row['window_visible'] for row in results)}
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    if options.max_ready_seconds is not None and median > options.max_ready_seconds:
        raise SystemExit(f'Startup {median:.3f}s exceeds local target {options.max_ready_seconds:.3f}s')


if __name__ == '__main__':
    main()
