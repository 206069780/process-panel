"""Build-time icon and Windows elevation helpers."""

import ctypes
import os
from pathlib import Path
import sys


def launch_admin():
    from ctypes import wintypes
    launch = ctypes.windll.shell32.ShellExecuteW
    launch.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                       wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
    launch.restype = wintypes.HINSTANCE
    previous = os.environ.get('PYINSTALLER_RESET_ENVIRONMENT')
    # An independently running onefile instance must own its extraction folder.
    os.environ['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    try:
        result = launch(None, 'runas', sys.executable, None, str(Path(sys.executable).parent), 0)
        return (result or 0) > 32
    finally:
        if previous is None:
            os.environ.pop('PYINSTALLER_RESET_ENVIRONMENT', None)
        else:
            os.environ['PYINSTALLER_RESET_ENVIRONMENT'] = previous


def icon_image():
    from PIL import Image, ImageDraw
    image = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((10, 10, 246, 246), radius=59, fill='#8be2ba')
    ink = '#173b2b'
    draw.rounded_rectangle((76, 76, 180, 180), radius=12, outline=ink, width=14)
    draw.rounded_rectangle((111, 111, 145, 145), radius=4, fill=ink)
    for value in (104, 152):
        for start, end in [((value, 51), (value, 77)), ((value, 180), (value, 206)),
                           ((51, value), (77, value)), ((180, value), (206, value))]:
            draw.line((start, end), fill=ink, width=13)
    return image
