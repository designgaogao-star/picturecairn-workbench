# -*- mode: python ; coding: utf-8 -*-
"""One-directory V2 backend: no Python installation or network required at runtime."""
import os

TOOL = os.path.abspath(os.path.join(SPECPATH, '..'))
a = Analysis(
    [os.path.join(TOOL, 'gallery', '__main__.py')], pathex=[TOOL], binaries=[],
    datas=[(os.path.join(TOOL, 'prototype'), 'prototype'),
           (os.path.join(TOOL, 'gallery', 'sql'), 'gallery/sql')],
    hiddenimports=['uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.h11_impl',
                   'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on',
                   'pythoncom', 'pywintypes', 'win32com.shell.shell', 'win32com.shell.shellcon'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'pandas', 'IPython', 'torch', 'tensorflow', 'jax',
              'numba', 'llvmlite', 'pytest', 'PyQt5', 'PySide6', 'wx'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='gallery_server', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='gallery_server')
