"""Rutas de recursos y datos para MKClips, fuente o distribución congelada."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def recursos_dir() -> Path:
    """Raíz de archivos de solo lectura incluidos en la aplicación."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def datos_dir() -> Path:
    """Raíz de archivos editables; conserva la ubicación histórica en desarrollo."""
    if getattr(sys, "frozen", False):
        if sys.platform.startswith("win"):
            base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        ruta = base / "MKClips"
    else:
        ruta = Path(__file__).resolve().parent
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def comando_python(script, args=()):
    """Comando uniforme para ejecutar un script del proyecto en otro proceso."""
    nombre = os.fspath(script)
    if getattr(sys, "frozen", False):
        return [sys.executable, "--ejecutar", nombre, *map(os.fspath, args)]
    ruta = Path(nombre)
    if not ruta.is_absolute():
        ruta = recursos_dir() / ruta
    return [sys.executable, str(ruta), *map(os.fspath, args)]


def preparar_entorno_empaquetado() -> None:
    """Envía cachés de modelos y WebView a la carpeta de datos del usuario."""
    if not getattr(sys, "frozen", False):
        return
    datos = datos_dir()
    modelos = datos / "modelos"
    if sys.platform.startswith("win"):
        (datos / "WebView2").mkdir(parents=True, exist_ok=True)
    modelos.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(modelos / "huggingface"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(modelos / "huggingface" / "hub"))
    if str(datos) not in sys.path:
        sys.path.insert(0, str(datos))
    config = datos / "config.py"
    ejemplo = recursos_dir() / "scripts" / "config_ejemplo.py"
    if not config.is_file() and ejemplo.is_file():
        config.write_text(ejemplo.read_text(encoding="utf-8"), encoding="utf-8")
    bin_dir = Path(sys.executable).resolve().parent / "bin"
    ffmpeg = bin_dir / ("ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg")
    if ffmpeg.is_file():
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")

