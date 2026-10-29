"""Punto de entrada para desarrollo y para MKClips.exe."""
from __future__ import annotations

import multiprocessing
import runpy
import shutil
import sys
from pathlib import Path

from rutas_app import datos_dir, preparar_entorno_empaquetado, recursos_dir


def main() -> None:
    multiprocessing.freeze_support()
    preparar_entorno_empaquetado()
    args = sys.argv[1:]
    if args and args[0] == "--ejecutar":
        if not getattr(sys, "frozen", False):
            raise SystemExit("--ejecutar solo está disponible en MKClips.exe")
        if len(args) < 2:
            raise SystemExit("Uso: MKClips.exe --ejecutar <script> [argumentos…]")
        nombre = Path(args[1])
        if nombre.is_absolute() or ".." in nombre.parts or nombre.suffix != ".py":
            raise SystemExit("Ruta de script no válida")
        origen = recursos_dir() / "scripts" / nombre
        if not origen.is_file():
            origen = recursos_dir() / nombre
        if not origen.is_file():
            raise SystemExit(f"No se encontró el script incluido: {nombre}")
        # Algunos scripts antiguos derivan BASE_DIR de __file__ y escriben
        # datos relativos a su directorio. Ejecutar una copia en APPDATA mantiene
        # esos comportamientos sin escribir dentro de los recursos del exe.
        runtime_dir = datos_dir()
        ruta = runtime_dir / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, ruta)
        sys.argv = [str(ruta), *args[2:]]
        rutas_import = [str(recursos_dir() / "scripts"), str(runtime_dir)]
        sys.path[:] = rutas_import + [p for p in sys.path if p not in rutas_import]
        runpy.run_path(str(ruta), run_name="__main__")
        return
    # PyInstaller stores runtime modules in its PYZ archive. ``run_path`` cannot
    # execute a .py resource inside _internal as a script directory, so invoke
    # the bundled module through Python's importer instead.
    sys.argv = ["configuracion_app.py", *args]
    sys.path.insert(0, str(recursos_dir() / "scripts"))
    runpy.run_module("configuracion_app", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
