# -*- coding: utf-8 -*-
"""Lanza una URL en Microsoft Edge como ventana de aplicación, sin usar el navegador predeterminado."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlparse


def _version_key(path: Path):
    return tuple(int(x) for x in re.findall(r"\d+", path.name))


def encontrar_edge():
    candidatos = []
    for nombre in ("msedge.exe", "msedge"):
        hallado = shutil.which(nombre)
        if hallado:
            candidatos.append(Path(hallado))
    if os.name == "nt":
        try:
            import winreg
            rutas = (
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
            )
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for ruta in rutas:
                    try:
                        with winreg.OpenKey(hive, ruta) as key:
                            valor, _ = winreg.QueryValueEx(key, None)
                            candidatos.append(Path(valor))
                    except OSError:
                        pass
        except ImportError:
            pass
        for variable, defecto in (("PROGRAMFILES(X86)", "C:/Program Files (x86)"),
                                  ("PROGRAMFILES", "C:/Program Files"),
                                  ("LOCALAPPDATA", "")):
            raiz = Path(os.environ.get(variable, defecto))
            if not str(raiz):
                continue
            candidatos.extend((raiz / "Microsoft/Edge/Application/msedge.exe",
                               raiz / "Microsoft/Edge Beta/Application/msedge.exe",
                               raiz / "Microsoft/Edge Dev/Application/msedge.exe"))
            core = raiz / "Microsoft/EdgeCore"
            try:
                versiones = sorted((p for p in core.iterdir() if p.is_dir()), key=_version_key, reverse=True)
                candidatos.extend(p / "msedge.exe" for p in versiones)
            except OSError:
                pass
    vistos = set()
    for candidato in candidatos:
        try:
            resuelta = candidato.resolve()
            clave = os.path.normcase(str(resuelta))
            if clave not in vistos and resuelta.is_file():
                vistos.add(clave)
                return str(resuelta)
        except OSError:
            continue
    return None


def abrir_en_edge(url):
    """Abre solo en Edge --app. Nunca recurre a webbrowser ni al navegador predeterminado."""
    destino = urlparse(str(url))
    if destino.scheme not in ("http", "https") or not destino.netloc:
        return False, "El enlace no es una URL HTTP válida."
    edge = encontrar_edge()
    if not edge:
        return False, "Microsoft Edge no está disponible. Instala Edge para abrir la tip page sin usar Chrome."
    try:
        subprocess.Popen([edge, f"--app={url}", "--new-window", "--no-first-run", "--no-default-browser-check"],
                         close_fds=True)
        return True, ""
    except OSError as exc:
        return False, f"No se pudo iniciar Microsoft Edge: {exc}"


def abrir_en_navegador_predeterminado(url):
    """Abre una URL externa mediante el navegador asociado en Windows."""
    destino = urlparse(str(url))
    if destino.scheme not in ("http", "https") or not destino.netloc:
        return False, "El enlace no es una URL HTTP válida."
    try:
        if webbrowser.open(str(url), new=2, autoraise=True):
            return True, ""
        return False, "Windows no pudo abrir el navegador predeterminado."
    except Exception as exc:
        return False, f"No se pudo abrir el navegador predeterminado: {exc}"
