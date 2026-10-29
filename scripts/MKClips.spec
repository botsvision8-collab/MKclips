# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve()
webview_datas, webview_binaries, webview_hidden = collect_all("webview")

# The Flask UI and clip editor are loaded from files at runtime, so include
# their complete folders alongside the frozen Python modules.
app_datas = [
    (str(ROOT / "ui_web"), "ui_web"),
    (str(ROOT / "editor_web"), "editor_web"),
    (str(ROOT / "OBS"), "OBS"),
    (str(ROOT.parent / "assets" / "models"), "assets/models"),
    (str(ROOT.parent / "VERSION"), "VERSION"),
]
app_datas.extend(
    (str(p), "scripts")
    for p in ROOT.glob("*.py")
    if p.name != "__init__.py" and p.name != "config.py" and not p.name.startswith("test_")
)

# Many pipeline routes use runtime imports. Bundle the project's modules so
# those pages keep working when launched from the frozen desktop app.
project_modules = sorted(
    p.stem for p in ROOT.glob("*.py") if p.stem != "__init__"
)
hidden = sorted(set(project_modules + webview_hidden))

a = Analysis(
    [str(ROOT / "configuracion_app.py")],
    pathex=[str(ROOT)],
    binaries=webview_binaries,
    datas=webview_datas + app_datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6", "gi", "cefpython3"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MKClips",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MKClips",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="MKClips.app",
        bundle_identifier="com.mkclips.desktop",
    )
