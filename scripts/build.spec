# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from pathlib import Path

block_cipher = None

project_dir = Path(os.getcwd())
icon_path = project_dir / "assets" / "icon.ico"

a = Analysis(
    [str(project_dir / "main.py")],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[
        (str(project_dir / "config" / "config.json"), "config"),
        (str(project_dir / "assets" / "icon.ico"), "assets"),
        (str(project_dir / "assets" / "rotation-guide.png"), "assets"),
    ],
    hiddenimports=[
        "openpyxl",
        "openpyxl.cell._writer",
        "openpyxl.reader.excel",
        "win32gui",
        "win32con",
        "pyautogui",
        "pkg_resources",
        "sqlite3",
        "ctypes",
        "json",
        "numpy",
        "scipy.spatial",
        "cryptography",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        "license.fingerprint",
        "license.verify",
        "license.state",
        "license.gate",
        "license.info",
        "license.activation_dialog",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "tkinter.*",
        "matplotlib",
        "matplotlib.*",
        "PIL",
        "PIL.*",
        "pandas",
        "pandas.*",
        "notebook",
        "notebook.*",
        "IPython",
        "IPython.*",
        "setuptools",
        "setuptools.*",
        "pip",
        "pip.*",
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="CAM350_Review",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
)
