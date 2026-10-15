# Windows desktop bundle. Directory mode avoids extraction on every launch.
from pathlib import Path
import os
import sys

root = Path(SPECPATH)
single_file = os.environ.get('PORTSIDE_SINGLE_FILE') == '1'
# Build from the app and Windows runtimes only. Developer tools can put a
# different ICU DLL on PATH, which has incompatible exports for Qt's OS ICU.
windows = Path(os.environ['SystemRoot'])
os.environ['PATH'] = os.pathsep.join((str(Path(sys.executable).parent),
                                    str(windows / 'System32'), str(windows)))
a = Analysis(
    [str(root / 'main.py')],
    pathex=[str(root)], binaries=[],
    datas=[(str(root / 'static'), 'static')],
    hiddenimports=[],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['tkinter', 'pystray'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe_options = dict(
    name='Portside', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
    icon=str(root / 'assets' / 'portside.ico'),
    version=str(root / 'windows-version.txt'),
    uac_admin=False,
)
if single_file:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **exe_options)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_options)
    bundle = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Portside')
