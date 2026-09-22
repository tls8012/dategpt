# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH).parent
desktop_dir = project_root / "desktop"
backend_dir = project_root / "BACKEND"

datas = [
    (
        str(project_root / ".scaffolding"),
        ".scaffolding",
    ),
    (
        str(desktop_dir / "style.qss"),
        "desktop",
    ),
]
binaries = []
hiddenimports = []

# LangChain discovers provider integrations dynamically. Collect both
# supported providers explicitly so packaged builds do not depend on imports
# that happened to be visible during Analysis.
for package_name in (
    "langchain_openai",
    "langchain_anthropic",
):
    package_datas, package_binaries, package_hidden = (
        collect_all(package_name)
    )
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden


a = Analysis(
    [str(desktop_dir / "main.py")],
    pathex=[
        str(desktop_dir),
        str(backend_dir),
    ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DateGPT",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    hide_console=(
        "hide-early"
        if sys.platform == "win32"
        else None
    ),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DateGPT",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="DateGPT.app",
        bundle_identifier="io.dategpt.desktop",
        version="0.1.0",
        info_plist={
            "NSHighResolutionCapable": True,
        },
    )
