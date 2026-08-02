# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

project_dir = Path(os.getcwd())

a = Analysis(
    [str(project_dir / "tools" / "license_cli.py")],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "cryptography",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        "license.verify",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6",
        "PySide6.*",
        "openpyxl",
        "numpy",
        "scipy",
        "tkinter",
        "tkinter.*",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="license_cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
