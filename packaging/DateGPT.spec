# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH).parent
desktop_dir = project_root / "desktop"
backend_dir = project_root / "BACKEND"

provider_datas = []
provider_binaries = []
provider_hiddenimports = []

for package_name in (
    "langchain_openai",
    "langchain_anthropic",
    "pydantic_core",
):
    package_datas, package_binaries, package_hidden = (
        collect_all(package_name)
    )
    provider_datas += package_datas
    provider_binaries += package_binaries
    provider_hiddenimports += package_hidden


gui_a = Analysis(
    [str(desktop_dir / "main.py")],
    pathex=[
        str(desktop_dir),
        str(backend_dir),
    ],
    binaries=[],
    datas=[
        (
            str(desktop_dir / "style.qss"),
            "desktop",
        ),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

worker_a = Analysis(
    [str(backend_dir / "backend.py")],
    pathex=[
        str(desktop_dir),
        str(backend_dir),
    ],
    binaries=provider_binaries,
    datas=[
        (
            str(project_root / ".scaffolding"),
            ".scaffolding",
        ),
        *provider_datas,
    ],
    hiddenimports=[
        *provider_hiddenimports,
        "pydantic_core._pydantic_core",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

gui_pyz = PYZ(gui_a.pure)
worker_pyz = PYZ(worker_a.pure)

gui_exe = EXE(
    gui_pyz,
    gui_a.scripts,
    [],
    exclude_binaries=True,
    name="DateGPT",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

worker_exe = EXE(
    worker_pyz,
    worker_a.scripts,
    [],
    exclude_binaries=True,
    name="DateGPTWorker",
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
    gui_exe,
    worker_exe,
    gui_a.binaries,
    gui_a.datas,
    worker_a.binaries,
    worker_a.datas,
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
            "LSUIElement": False,
            "LSBackgroundOnly": False,
        },
    )
