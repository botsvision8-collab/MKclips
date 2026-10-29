# -*- coding: utf-8 -*-
"""Abre un video con el reproductor predeterminado del sistema operativo.

Windows: el programa asociado al tipo de archivo (Películas y TV, VLC...).
macOS:   ``open``.
Linux:   ``xdg-open``.

El reproductor lo controla el sistema, así que el tamaño de la ventana y la
sincronización de audio y video dependen de él. MKClips no lo vuelve a abrir
ni lo cierra: cada llamada lanza el programa y devuelve el control.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys


def abrir_en_reproductor(ruta):
    """Abre ``ruta`` con el reproductor del sistema. Devuelve ``(ok, mensaje)``."""
    if not ruta or not os.path.isfile(ruta):
        return False, "El archivo del clip ya no existe."
    ruta = os.path.abspath(ruta)
    try:
        if sys.platform.startswith("win"):
            os.startfile(ruta)  # noqa: S606 - abre con la aplicación asociada
        elif sys.platform == "darwin":
            subprocess.Popen(["open", ruta], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            lanzador = shutil.which("xdg-open")
            if not lanzador:
                return False, "No se encontró xdg-open para abrir el video con el reproductor del sistema."
            subprocess.Popen([lanzador, ruta], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except OSError as exc:
        return False, (
            "El sistema no pudo abrir el video: "
            f"{exc}\nComprueba que tengas un reproductor asociado a este tipo de archivo."
        )
    return True, ""
