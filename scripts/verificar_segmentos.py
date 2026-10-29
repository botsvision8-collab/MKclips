# -*- coding: utf-8 -*-
"""
MKClips - Verificación post-render de edición por segmentos.

Lee clips_sugeridos.json, localiza los MP4/MKV generados y compara:
1) suma de duraciones de "segmentos";
2) duración del intervalo continuo fin-inicio;
3) duración real del archivo mediante ffprobe.

Rutas:
- Clips: CARPETA_CLIPS_BASE desde config.py.
- Override opcional: variable de entorno MKCLIPS_CLIPS_DIR.
- Resultados: scripts\resultados por defecto.
- Override opcional: MKCLIPS_RESULTADOS_DIR.

No modifica clips ni los JSON de entrada.
Genera resultados\validacion_segmentos.json
"""

import json
import math
from cache_mkclips import exigir_identidad_artefacto
from evidencia_render import verificar_render, comprobar_correspondencia
from config import DURACION_MIN_CLIP, DURACION_MAX_CLIP
import os
import subprocess
import sys
from pathlib import Path

from narrativa_mkclips import normalizar_segmentos_sin_duplicados

BASE_DIR = Path(__file__).resolve().parent

try:
    from config import CARPETA_CLIPS_BASE as _CARPETA_CLIPS_CONFIG, CARPETA_RESULTADOS as _CARPETA_RESULTADOS_CONFIG
except Exception:
    _CARPETA_CLIPS_CONFIG = ""
    _CARPETA_RESULTADOS_CONFIG = ""

CARPETA_CLIPS_BASE = Path(
    os.environ.get("MKCLIPS_CLIPS_DIR", _CARPETA_CLIPS_CONFIG or "")
).expanduser()

RESULTADOS_DIR = Path(
    os.environ.get("MKCLIPS_RESULTADOS_DIR", _CARPETA_RESULTADOS_CONFIG or str(BASE_DIR / "resultados"))
).expanduser()

ARCHIVO_JSON = RESULTADOS_DIR / "clips_sugeridos.json"
ARCHIVO_VALIDACION = RESULTADOS_DIR / "validacion_segmentos.json"
TOLERANCIA_SEGUNDOS = float(
    os.environ.get("MKCLIPS_SEGMENT_TOLERANCE", "0.25")
)


def cargar_clips():
    if ARCHIVO_JSON.exists():
        with ARCHIVO_JSON.open("r", encoding="utf-8") as f:
            return json.load(f)

    legado = BASE_DIR / "clips_sugeridos.json"
    if legado.exists():
        print(
            f"ADVERTENCIA: no se encontró {ARCHIVO_JSON}; "
            f"usando archivo legado: {legado}"
        )
        with legado.open("r", encoding="utf-8") as f:
            return json.load(f)

    raise FileNotFoundError(
        f"No se encontró clips_sugeridos.json en {ARCHIVO_JSON} "
        f"ni en {legado}."
    )


def _nombre_archivo_seguro(texto, indice):
    texto = str(texto).strip().lower()
    reemplazos = {
        "á": "a", "à": "a", "ä": "a",
        "é": "e", "è": "e", "ë": "e",
        "í": "i", "ì": "i", "ï": "i",
        "ó": "o", "ò": "o", "ö": "o",
        "ú": "u", "ù": "u", "ü": "u",
        "ñ": "n",
    }
    for viejo, nuevo in reemplazos.items():
        texto = texto.replace(viejo, nuevo)

    texto = "".join(
        ch for ch in texto
        if ch.isascii() and (ch.isalnum() or ch in " -_")
    )
    while "  " in texto:
        texto = texto.replace("  ", " ")
    texto = texto.replace(" ", "_").strip("_")

    if not texto:
        texto = "clip"

    return f"{indice:02d}_{texto[:50]}"


def obtener_archivo_clip(clip, indice):
    posibles = []

    for clave in ("ruta_archivo", "archivo"):
        archivo = clip.get(clave)
        if isinstance(archivo, str) and archivo.strip():
            posibles.append(Path(archivo.strip()))

    # Las rutas relativas se interpretan primero respecto a scripts.
    posibles = [p if p.is_absolute() else BASE_DIR / p for p in posibles]

    nombre = _nombre_archivo_seguro(clip.get("titulo", "clip"), indice)
    posibles.extend(
        [Path(nombre + ".mkv"), Path(nombre + ".mp4")]
    )

    for candidato in posibles:
        if candidato.is_absolute() and candidato.exists():
            return candidato
        if CARPETA_CLIPS_BASE:
            directo = CARPETA_CLIPS_BASE / candidato
            if directo.exists():
                return directo

    if CARPETA_CLIPS_BASE.exists():
        nombre_video = str(clip.get("stream", "")).strip()
        if nombre_video:
            carpeta_video = CARPETA_CLIPS_BASE / Path(nombre_video).stem
            for candidato in posibles:
                p = carpeta_video / candidato.name
                if p.exists():
                    return p

        for candidato in posibles:
            encontrados = list(
                CARPETA_CLIPS_BASE.rglob(candidato.name)
            )
            if encontrados:
                return encontrados[0]

    return None


def duracion_ffprobe(archivo):
    comando = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(archivo),
    ]

    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "ffprobe no está disponible en PATH. "
            "Instala/activa FFmpeg antes de ejecutar la verificación."
        )

    if resultado.returncode != 0:
        raise RuntimeError(
            f"ffprobe falló para '{archivo}': "
            f"{(resultado.stderr or '').strip()}"
        )

    valor = (resultado.stdout or "").strip()
    try:
        return float(valor)
    except ValueError:
        raise RuntimeError(
            f"ffprobe no devolvió una duración válida: {valor!r}"
        )


def analizar_segmentos(clip):
    segmentos = clip.get("segmentos")
    if not isinstance(segmentos, list) or not segmentos:
        return None

    duracion = 0.0
    normalizados = []

    for posicion, segmento in enumerate(segmentos, start=1):
        if not isinstance(segmento, dict):
            raise ValueError(
                f"segmento #{posicion} no es un objeto."
            )

        inicio = float(segmento["inicio"])
        fin = float(segmento["fin"])

        if not math.isfinite(inicio) or not math.isfinite(fin) or inicio < 0 or fin <= inicio:
            raise ValueError(
                f"segmento #{posicion} inválido: "
                f"inicio={inicio}, fin={fin}"
            )

        duracion += fin - inicio
        normalizados.append({
            "inicio": inicio,
            "fin": fin,
        })

    inicio_global = float(
        clip.get("inicio", normalizados[0]["inicio"])
    )
    fin_global = float(
        clip.get("fin", normalizados[-1]["fin"])
    )

    sin_duplicados = normalizar_segmentos_sin_duplicados(normalizados)
    if sin_duplicados != normalizados:
        raise ValueError("contiene segmentos duplicados, contenidos o solapados sin normalizar")

    return {
        "segmentos": normalizados,
        "duracion_esperada": duracion,
        "duracion_span_continuo": max(
            0.0, fin_global - inicio_global
        ),
        "inicio_global": inicio_global,
        "fin_global": fin_global,
    }


def main():
    print("=== MKClips — Validación de edición por segmentos ===")
    print(f"Scripts:    {BASE_DIR}")
    print(f"Resultados: {RESULTADOS_DIR}")
    print(
        "Clips:      "
        + (str(CARPETA_CLIPS_BASE)
           if CARPETA_CLIPS_BASE else "NO CONFIGURADA")
    )
    print()

    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        clips = cargar_clips()
        video = (BASE_DIR / "ultimo_video.txt").read_text(encoding="utf-8").splitlines()[0]
        fuente = exigir_identidad_artefacto(str(ARCHIVO_JSON), video, "clips_sugeridos")
        ruta_resumen = RESULTADOS_DIR / "resumen_plan.json"
        if ruta_resumen.is_file():
            exigir_identidad_artefacto(str(ruta_resumen), video, "resumen_plan")
            resumen = json.loads(ruta_resumen.read_text(encoding="utf-8"))
            if resumen.get("momentos"):
                segmentos_resumen = [{"inicio": s["inicio"], "fin": s["fin"]} for s in resumen["momentos"]]
                clips.append({**resumen, "segmentos": segmentos_resumen,
                              "inicio": segmentos_resumen[0]["inicio"], "fin": segmentos_resumen[-1]["fin"]})
    except Exception as e:
        print(f"ERROR: {e}")
        return 2

    if not isinstance(clips, list):
        print("ERROR: clips_sugeridos.json no contiene una lista.")
        return 2

    registros = []
    con_segmentos = 0
    correctos = 0
    errores = 0
    no_demostrables = 0

    for indice, clip in enumerate(clips, start=1):
        if not isinstance(clip, dict) or not clip.get("segmentos"):
            registros.append({
                "indice": indice,
                "titulo": str(clip.get("titulo", f"Clip {indice}")) if isinstance(clip, dict) else f"Clip {indice}",
                "estado": "CONTRATO_INVALIDO",
                "motivo": "Un clip final no tiene segmentos reales persistidos.",
            })
            errores += 1
            continue

        con_segmentos += 1
        titulo = str(clip.get("titulo", f"Clip {indice}"))
        registro = {
            "indice": indice,
            "titulo": titulo,
            "estado": "NO_DEMOSTRABLE",
        }

        try:
            datos = analizar_segmentos(clip)
            registro.update(datos)
            duracion = datos["duracion_esperada"]
            if (DURACION_MIN_CLIP and duracion < DURACION_MIN_CLIP - 0.001) or (DURACION_MAX_CLIP and duracion > DURACION_MAX_CLIP + 0.001):
                raise ValueError("Duración de segmentos únicos fuera de MIN/MAX")
            declarada = clip.get("duracion")
            if declarada is not None and abs(float(declarada) - registro["duracion_esperada"]) > TOLERANCIA_SEGUNDOS:
                raise ValueError("duracion declarada no coincide con la suma de segmentos")

            archivo = obtener_archivo_clip(clip, indice)
            registro["archivo"] = (
                str(archivo) if archivo else None
            )

            if archivo is None:
                registro["motivo"] = (
                    "No se encontró el MP4/MKV correspondiente."
                )
                no_demostrables += 1
                print(
                    f"[{indice}] {titulo}: NO DEMOSTRABLE "
                    "(archivo final no encontrado)"
                )
                registros.append(registro)
                continue

            registro["evidencia_render"] = verificar_render(archivo, datos["segmentos"], fuente)
            registro["correspondencia_visual"] = comprobar_correspondencia(archivo, datos["segmentos"], video)
            registro["provenance"] = fuente
            sello = archivo.stat()
            registro["archivo_size"] = sello.st_size
            registro["archivo_mtime_ns"] = sello.st_mtime_ns
            real = duracion_ffprobe(archivo)
            diferencia = abs(
                real - registro["duracion_esperada"]
            )

            registro["duracion_real_mp4"] = real
            registro["diferencia_vs_esperado"] = diferencia

            if diferencia <= TOLERANCIA_SEGUNDOS:
                registro["estado"] = "CORRECTO"
                registro["motivo"] = (
                    "La duración real coincide con la suma "
                    "de los segmentos."
                )
                correctos += 1
                print(
                    f"[{indice}] {titulo}: CORRECTO | "
                    f"esperado={registro['duracion_esperada']:.3f}s | "
                    f"real={real:.3f}s | "
                    f"span={registro['duracion_span_continuo']:.3f}s"
                )
            else:
                registro["estado"] = "ERROR"
                registro["motivo"] = (
                    "La duración real no coincide con la suma "
                    "de los segmentos."
                )
                errores += 1
                print(
                    f"[{indice}] {titulo}: ERROR | "
                    f"esperado={registro['duracion_esperada']:.3f}s | "
                    f"real={real:.3f}s | "
                    f"span={registro['duracion_span_continuo']:.3f}s"
                )

        except Exception as e:
            registro["estado"] = "ERROR"
            registro["motivo"] = str(e)
            errores += 1
            print(f"[{indice}] {titulo}: ERROR | {e}")

        registros.append(registro)

    if con_segmentos == 0:
        estado_global = "CONTRATO_INVALIDO"
    elif errores:
        estado_global = "ERROR"
    elif no_demostrables:
        estado_global = "PARCIAL"
    else:
        estado_global = "CONFIRMADO"

    informe = {
        "version": "mkclips-validacion-segmentos-v2",
        "fuente": fuente,
        "valoracion_manual": "PENDIENTE: no se infiere calidad narrativa o audiovisual de la validación técnica",
        "estado": estado_global,
        "tolerancia_segundos": TOLERANCIA_SEGUNDOS,
        "clips_con_segmentos": con_segmentos,
        "clips_correctos": correctos,
        "clips_error": errores,
        "clips_no_demostrables": no_demostrables,
        "resultados": registros,
    }

    with ARCHIVO_VALIDACION.open("w", encoding="utf-8") as f:
        json.dump(informe, f, ensure_ascii=False, indent=2)

    print()
    print("=== RESULTADO ===")
    print(f"Estado global:       {estado_global}")
    print(f"Con segmentos:       {con_segmentos}")
    print(f"Correctos:           {correctos}")
    print(f"Errores:             {errores}")
    print(f"No demostrables:     {no_demostrables}")
    print(f"Informe:             {ARCHIVO_VALIDACION}")

    return 0 if estado_global == "CONFIRMADO" else 1


if __name__ == "__main__":
    sys.exit(main())
