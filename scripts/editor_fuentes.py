# -*- coding: utf-8 -*-
"""Tipografías instaladas en el equipo, para los subtítulos del editor.

Lee el nombre de familia directamente de los archivos .ttf/.otf/.ttc (solo la tabla
``name``, sin dependencias externas). El navegador del editor usa esos mismos nombres
porque las fuentes ya están instaladas; para el render, ``preparar_carpeta_fuentes``
copia solo los archivos de la fuente elegida a una carpeta que lee libass (FFmpeg).
"""
from __future__ import annotations

import os
import shutil
import struct
import sys
import threading

EXTENSIONES_FUENTE = (".ttf", ".otf", ".ttc", ".otc")
_CACHE = {"fuentes": None}
_BLOQUEO = threading.Lock()


def carpetas_de_fuentes():
    """Carpetas donde el sistema operativo guarda las fuentes instaladas."""
    carpetas = []
    if sys.platform.startswith("win"):
        carpetas.append(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            carpetas.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    elif sys.platform == "darwin":
        carpetas += ["/System/Library/Fonts", "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
    else:
        carpetas += ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
                     os.path.expanduser("~/.local/share/fonts")]
    return [c for c in carpetas if os.path.isdir(c)]


def _texto(registro_bytes, plataforma):
    try:
        if plataforma in (0, 3):
            return registro_bytes.decode("utf-16-be")
        return registro_bytes.decode("mac_roman")
    except UnicodeDecodeError:
        return registro_bytes.decode("latin-1", "replace")


def _nombres_de_fuente(datos, desplazamiento):
    """{id_nombre: texto} de la tabla ``name`` de la fuente que empieza en ``desplazamiento``."""
    if len(datos) < desplazamiento + 12:
        return {}
    num_tablas = struct.unpack(">H", datos[desplazamiento + 4:desplazamiento + 6])[0]
    tabla = None
    for i in range(num_tablas):
        base = desplazamiento + 12 + i * 16
        if base + 16 > len(datos):
            break
        etiqueta, _suma, inicio, largo = struct.unpack(">4sIII", datos[base:base + 16])
        if etiqueta == b"name":
            tabla = (inicio, largo)
            break
    if not tabla or tabla[0] + 6 > len(datos):
        return {}
    inicio, _largo = tabla
    _formato, cuenta, desplazamiento_textos = struct.unpack(">HHH", datos[inicio:inicio + 6])
    candidatos = {}
    for i in range(cuenta):
        base = inicio + 6 + i * 12
        if base + 12 > len(datos):
            break
        plataforma, _codificacion, idioma, id_nombre, largo_texto, desp = struct.unpack(">HHHHHH", datos[base:base + 12])
        if id_nombre not in (1, 2, 4, 16, 17):
            continue
        crudo = datos[inicio + desplazamiento_textos + desp:inicio + desplazamiento_textos + desp + largo_texto]
        valor = _texto(crudo, plataforma).strip().strip("\x00")
        if not valor:
            continue
        # Se prefiere inglés de Windows (0x409); si no hay, lo primero que aparezca.
        prioridad = 0 if (plataforma == 3 and idioma == 0x409) else 1 if plataforma == 3 else 2
        if id_nombre not in candidatos or prioridad < candidatos[id_nombre][0]:
            candidatos[id_nombre] = (prioridad, valor)
    return {k: v[1] for k, v in candidatos.items()}


def leer_fuente(ruta):
    """Lista de {"familia", "estilo", "negrita", "cursiva"} de un archivo de fuente (vacía si no se entiende)."""
    try:
        with open(ruta, "rb") as archivo:
            datos = archivo.read(4 * 1024 * 1024 if ruta.lower().endswith((".ttc", ".otc")) else 8 * 1024 * 1024)
    except OSError:
        return []
    desplazamientos = [0]
    if datos[:4] == b"ttcf" and len(datos) >= 12:
        cantidad = struct.unpack(">I", datos[8:12])[0]
        desplazamientos = [struct.unpack(">I", datos[12 + 4 * i:16 + 4 * i])[0] for i in range(min(cantidad, 32)) if len(datos) >= 16 + 4 * i]
    elif datos[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        return []
    resultado = []
    for desp in desplazamientos:
        try:
            nombres = _nombres_de_fuente(datos, desp)
        except (struct.error, IndexError):
            continue
        familia = nombres.get(16) or nombres.get(1)
        if not familia:
            continue
        estilo = nombres.get(17) or nombres.get(2) or "Regular"
        minuscula = f"{estilo} {nombres.get(4, '')}".lower()
        resultado.append({"familia": familia, "estilo": estilo,
                          "negrita": "bold" in minuscula or "negrita" in minuscula or "black" in minuscula,
                          "cursiva": "italic" in minuscula or "oblique" in minuscula or "cursiva" in minuscula})
    return resultado


def listar_fuentes(refrescar=False, carpetas=None):
    """Familias instaladas: [{"familia", "archivos": [ruta, ...], "estilos": [..]}] ordenadas por nombre."""
    with _BLOQUEO:
        if _CACHE["fuentes"] is not None and not refrescar and carpetas is None:
            return _CACHE["fuentes"]
        familias = {}
        for carpeta in (carpetas if carpetas is not None else carpetas_de_fuentes()):
            for raiz, _dirs, archivos in os.walk(carpeta):
                for nombre in archivos:
                    if not nombre.lower().endswith(EXTENSIONES_FUENTE) or nombre.startswith("."):
                        continue
                    ruta = os.path.join(raiz, nombre)
                    for info in leer_fuente(ruta):
                        clave = info["familia"].casefold()
                        entrada = familias.setdefault(clave, {"familia": info["familia"], "archivos": [], "estilos": []})
                        if ruta not in entrada["archivos"]:
                            entrada["archivos"].append(ruta)
                        if info["estilo"] not in entrada["estilos"]:
                            entrada["estilos"].append(info["estilo"])
        resultado = sorted(familias.values(), key=lambda e: e["familia"].casefold())
        if carpetas is None:
            _CACHE["fuentes"] = resultado
        return resultado


def buscar_familia(familia, fuentes=None):
    """La entrada de ``familia`` (sin distinguir mayúsculas) o None."""
    clave = str(familia or "").casefold()
    for entrada in (fuentes if fuentes is not None else listar_fuentes()):
        if entrada["familia"].casefold() == clave:
            return entrada
    return None


def fuente_por_defecto(fuentes=None, preferidas=("Montserrat", "Arial", "Segoe UI", "Roboto", "Open Sans", "DejaVu Sans")):
    fuentes = fuentes if fuentes is not None else listar_fuentes()
    for nombre in preferidas:
        if buscar_familia(nombre, fuentes):
            return nombre
    return fuentes[0]["familia"] if fuentes else "Arial"


def preparar_carpeta_fuentes(familia, destino, fuentes=None):
    """Copia a ``destino`` los archivos de ``familia`` (para ``ass=...:fontsdir=``).

    Devuelve cuántos archivos copió; 0 si la fuente no está instalada (libass usará su
    fuente por defecto en ese caso)."""
    entrada = buscar_familia(familia, fuentes)
    if not entrada:
        return 0
    os.makedirs(destino, exist_ok=True)
    copiados = 0
    for ruta in entrada["archivos"]:
        try:
            shutil.copy2(ruta, os.path.join(destino, os.path.basename(ruta)))
            copiados += 1
        except OSError:
            continue
    return copiados
