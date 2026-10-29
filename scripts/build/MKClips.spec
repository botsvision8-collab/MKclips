# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all

SCRIPTS = Path(SPECPATH).resolve().parent.parent / "scripts"
PROJECT = SCRIPTS.parent
datas, binaries, hidden = [], [], []
for package in ("webview",):
    d, b, h = collect_all(package)
    datas += d; binaries += b; hidden += h

# El config.py local es configuración privada del desarrollador. En el exe se
# crea una copia editable desde config_ejemplo.py dentro de %APPDATA%.
for source in SCRIPTS.rglob("*.py"):
    if (source.name == "config.py" or source.name.startswith("test_")
            or "pruebas_controladas" in source.parts or "__pycache__" in source.parts
            or ".venv" in source.parts or "build" in source.parts):
        continue
    datas.append((str(source), str(Path("scripts") / source.relative_to(SCRIPTS).parent)))
# Include only runtime web/static/template resources. User results, recordings,
# configuration, logs, caches, and model directories are never traversed.
resource_dirs = [SCRIPTS / "ui_web", SCRIPTS / "editor_web",
                 PROJECT / "static", PROJECT / "plantillas"]
for path in resource_dirs:
    if path.is_dir():
        destination = Path("scripts") / path.relative_to(SCRIPTS) if path.is_relative_to(SCRIPTS) else path.relative_to(PROJECT)
        for f in path.rglob("*"):
            if f.is_file() and not any(part in {"__pycache__", "resultados", "clips", "streams", "modelos"} for part in f.parts):
                datas.append((str(f), str(destination / f.relative_to(path).parent)))
for folder in ("assets",):
    path = PROJECT / folder
    for f in path.rglob("*"):
        if f.is_file() and not any(part in {"capturas", "diagnostico", "resultados", "clips", "streams", "modelos"} for part in f.parts):
            datas.append((str(f), str(Path(folder) / f.relative_to(path).parent)))
datas.append((str(PROJECT / "VERSION"), "."))
print("Recursos incluidos: scripts Python de la app; scripts/ui_web; scripts/editor_web; static y plantillas si existen; assets; VERSION; dependencias Python y WebView2 wrapper.")
print("Excluidos: config.py/config local, claves, resultados, clips, streams, transcripciones, criterios, logs, cachés, modelos y pruebas controladas.")
hidden += [p.stem for p in SCRIPTS.glob("*.py") if p.name not in {"config.py", "__init__.py"} and not p.name.startswith("test_")]
if sys.platform == "win32":
    hidden += ["webview.platforms.edgechromium", "clr", "pythonnet", "webview.platforms.winforms"]

a = Analysis([str(SCRIPTS / "mkclips_app.py")], pathex=[str(SCRIPTS)], binaries=binaries,
             datas=datas, hiddenimports=sorted(set(hidden)), hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=["config", "scripts.config", "torch", "torchvision", "torchaudio", "PyQt5", "PyQt6", "PySide2", "PySide6", "cefpython3"] + (["gi"] if sys.platform == "win32" else []),
             noarchive=False, optimize=1)
pyz = PYZ(a.pure)
app_icon = str(PROJECT / "assets" / "logo.ico") if sys.platform == "win32" else None
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="MKClips", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=app_icon, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="MKClips")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="MKClips.app", bundle_identifier="com.mkclips.desktop")
