# -*- coding: utf-8 -*-
"""PyInstaller 打包配置：把 Python 后端打成独立目录（--onedir）。

**为什么是 onedir 而不是 onefile**：
onefile 每次启动都要把 100MB+ 解压到临时目录，冷启动多 2-3 秒；
onedir 只是多一个文件夹，启动快得多。这个工具的启动体验本来就靠"秒开"。

**必须一起打包的资源**：
  · ui/           —— 前端 css/js
  · index.html / survey.html —— 页面模板
  · pkgpath.py    —— 图包名解析（被 scan / dedup 多处在跑时 import）

**数据目录不打包**（cache / thumbs / review_state.json）：
它们是用户数据，放在 exe 旁边（见 gallery/paths.py 的 APP_DIR / RES_DIR 区分）。

用法：
    python -m PyInstaller scripts/gallery.spec --noconfirm
"""
# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

TOOL = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(TOOL, "gallery_server.py")],
    pathex=[TOOL],
    binaries=[],
    # 资源文件：跑到 (目标目录, 源路径)
    datas=[
        (os.path.join(TOOL, "ui"), "ui"),
        (os.path.join(TOOL, "index.html"), "."),
        (os.path.join(TOOL, "survey.html"), "."),
    ],
    # 这些是运行时按需 import 的（字符串形式），静态分析看不到
    hiddenimports=[
        "PIL._imaging",
        "PIL.Image",
        "PIL.ImageOps",
        "gallery",
        "gallery.paths", "gallery.config", "gallery.store", "gallery.scan",
        "gallery.thumbs", "gallery.remove", "gallery.guard", "gallery.journal",
        "gallery.locks", "gallery.fileio",
        "gallery.api.review", "gallery.api.remove",
        "gallery.api.maintain", "gallery.api.dedup",
        "pkgpath", "dedup_build", "dedup_analyze", "dedup_verify", "dedup_husk",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 明显用不到的大件，砍掉能省几十 MB
        "tkinter", "matplotlib", "pandas", "IPython",
        "webview", "pythonnet", "clr_loader",
        "torch", "torchvision", "torchaudio", "tensorflow", "jax", "jaxlib",
        "cupy", "numba", "llvmlite", "dask", "fsspec", "h5py", "sympy",
        "pytest", "setuptools", "pip", "wheel",
        "PyQt5", "PySide2", "PySide6", "wx",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gallery_server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # 机械盘上 UPX 解压反而更慢，且杀软误报率高
    console=False,             # 无控制台；stdout/stderr 由 gallery_server 顶部接到 boot.log（Electron 会把它当 sidecar 拉起）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="gallery_server",
)
