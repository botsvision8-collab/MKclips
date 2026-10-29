import json
import subprocess
import os
import re
import sys
from datetime import datetime

from evidencia_render import registrar_render
import hardware_scheduler
from cache_mkclips import exigir_identidad_artefacto, guardar_identidad_artefacto
from narrativa_mkclips import normalizar_segmentos_sin_duplicados
from duracion_clips import recortar_segmentos_a_maximo
import catalogo_clips

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

try:
    from config import CARPETA_CLIPS_BASE, CARPETA_RESULTADOS, DURACION_MIN_CLIP, DURACION_MAX_CLIP
except ImportError:
    print("ADVERTENCIA: no se encontro config.py, usando valor generico.")
    print("Copia config_ejemplo.py como config.py y personalizalo.\n")
    CARPETA_CLIPS_BASE = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "clips")
    CARPETA_RESULTADOS = ""
    DURACION_MIN_CLIP = 0
    DURACION_MAX_CLIP = 0
if not DURACION_MAX_CLIP:
    print("AVISO: DURACION_MAX_CLIP = 0, los clips no tendran limite de duracion.")

CARPETA_RESULTADOS = CARPETA_RESULTADOS or os.path.join(BASE_DIR, "resultados")
ARCHIVO_HISTORIAL = os.path.join(BASE_DIR, "historial_clips.json")

UMBRAL_SILENCIO = 1.0
MARGEN_RESPIRO = 0.15

# Renderizado acelerado por la RTX 4060.
# h264_nvenc evita que el render dependa principalmente del CPU.
NVENC_ENCODER = os.environ.get("NVENC_ENCODER", "libx264" if sys.platform == "darwin" else "h264_nvenc")
NVENC_PRESET = os.environ.get("NVENC_PRESET", "p5")
NVENC_CQ = os.environ.get("NVENC_CQ", "21")
NVENC_AUDIO = os.environ.get("NVENC_AUDIO", "aac")

MODO_AUTOMATICO = os.environ.get("MODO_AUTOMATICO") == "1"

with open("ultimo_video.txt", "r", encoding="utf-8") as f:
    lineas = f.read().splitlines()
    video_path = lineas[0]
    nombre_video = lineas[1]

exigir_identidad_artefacto("transcripcion.json", video_path, "transcripcion")

with open("transcripcion.json", "r", encoding="utf-8") as f:
    todos_los_segmentos = json.load(f)

carpeta_salida = os.environ.get("MKCLIPS_RENDER_DIR") or os.path.join(CARPETA_CLIPS_BASE, nombre_video)
os.makedirs(carpeta_salida, exist_ok=True)

with open(os.path.join(CARPETA_RESULTADOS, "clips_sugeridos.json"), "r", encoding="utf-8") as f:
    clips = json.load(f)
exigir_identidad_artefacto(os.path.join(CARPETA_RESULTADOS, "clips_sugeridos.json"), video_path, "clips_sugeridos")

def contar_pistas_audio(video_path):
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", video_path],
        capture_output=True, text=True
    )
    lineas_out = [l for l in resultado.stdout.strip().splitlines() if l.strip()]
    return max(1, len(lineas_out))

NUM_PISTAS_AUDIO = contar_pistas_audio(video_path)
print(f"Detectadas {NUM_PISTAS_AUDIO} pista(s) de audio en el video original.")

def nombre_archivo_seguro(texto, indice):
    texto = texto.strip().lower()
    texto = re.sub(r'[áàä]', 'a', texto)
    texto = re.sub(r'[éèë]', 'e', texto)
    texto = re.sub(r'[íìï]', 'i', texto)
    texto = re.sub(r'[óòö]', 'o', texto)
    texto = re.sub(r'[úùü]', 'u', texto)
    texto = re.sub(r'[ñ]', 'n', texto)
    texto = re.sub(r'[^a-z0-9\s-]', '', texto)
    texto = re.sub(r'\s+', '_', texto).strip('_')
    if not texto:
        texto = "clip"
    return f"{indice:02d}_{texto[:50]}"

def calcular_rangos_a_mantener(inicio_clip, fin_clip, segmentos):
    relevantes = [s for s in segmentos if s["fin"] > inicio_clip and s["inicio"] < fin_clip]
    relevantes.sort(key=lambda s: s["inicio"])

    rangos = []
    inicio_tramo = inicio_clip
    cursor = inicio_clip
    for seg in relevantes:
        hueco = seg["inicio"] - cursor
        if hueco > UMBRAL_SILENCIO:
            fin_tramo = min(cursor + MARGEN_RESPIRO, fin_clip)
            if fin_tramo > inicio_tramo:
                rangos.append((inicio_tramo, fin_tramo))
            inicio_tramo = max(seg["inicio"] - MARGEN_RESPIRO, fin_tramo)
        cursor = max(cursor, min(seg["fin"], fin_clip))
    if inicio_tramo < fin_clip:
        rangos.append((inicio_tramo, fin_clip))

    return rangos

def construir_filtro_multipista(rangos_rel, num_pistas):
    """Genera un filtro trim+concat para el video Y para cada pista de audio
    por separado, manteniendo todas las pistas de audio originales intactas
    (no las mezcla en una sola)."""
    partes = []
    etiquetas_video = []
    cursor = 0.0
    for idx, (s, e) in enumerate(rangos_rel):
        # Posicionar cada frame en la línea de salida exacta evita acumular
        # redondeos de duración de video frente a audio entre cortes breves.
        partes.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-({s})/TB+({cursor:.6f})/TB[v{idx}]")
        etiquetas_video.append(f"[v{idx}]")
        cursor += e - s
    partes.append("".join(etiquetas_video) + f"interleave=n={len(rangos_rel)}:duration=longest[vout]")

    mapas_salida = ["[vout]"]
    for pista in range(num_pistas):
        etiquetas_audio = []
        for idx, (s, e) in enumerate(rangos_rel):
            partes.append(f"[0:a:{pista}]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{pista}_{idx}]")
            etiquetas_audio.append(f"[a{pista}_{idx}]")
        partes.append("".join(etiquetas_audio) + f"concat=n={len(rangos_rel)}:v=0:a=1[a{pista}out]")
        mapas_salida.append(f"[a{pista}out]")

    filtro = ";".join(partes)
    return filtro, mapas_salida

def _args_video_nvenc():
    """Argumentos comunes para codificar con NVENC en la RTX 4060."""
    if NVENC_ENCODER == "libx264":
        return ["-c:v", "libx264", "-preset", "medium", "-crf", NVENC_CQ,
                "-c:a", NVENC_AUDIO, "-fps_mode", "vfr"]
    return [
        "-c:v", NVENC_ENCODER,
        "-preset", NVENC_PRESET,
        "-rc", "vbr",
        "-cq", NVENC_CQ,
        "-b:v", "0",
        "-c:a", NVENC_AUDIO,
        "-fps_mode", "vfr",
    ]


def _ejecutar_ffmpeg(comando, salida_final):
    """Ejecuta FFmpeg (NVENC) bajo el scheduler de GPU compartido, y deja
    el error visible si falla."""
    with hardware_scheduler.gpu_slot("nvenc"):
        resultado = subprocess.run(
            comando,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
    if resultado.returncode != 0 and NVENC_ENCODER in ("h264_nvenc", "hevc_nvenc"):
        # Windows/Linux builds may include NVENC even when the current machine
        # has no compatible NVIDIA encoder. Retry the same render on the CPU.
        try:
            if os.path.exists(salida_final):
                os.remove(salida_final)
        except OSError:
            pass
        cpu = []
        i = 0
        while i < len(comando):
            arg = comando[i]
            if arg == "-c:v" and i + 1 < len(comando) and comando[i + 1] in ("h264_nvenc", "hevc_nvenc"):
                cpu += ["-c:v", "libx264", "-preset", "medium", "-crf", NVENC_CQ]
                i += 2
                continue
            if arg in ("-preset", "-rc", "-cq", "-b:v") and i + 1 < len(comando):
                i += 2
                continue
            cpu.append(arg)
            i += 1
        resultado = subprocess.run(
            cpu, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace"
        )
    if resultado.returncode != 0:
        print(f"  ERROR FFmpeg al generar {os.path.basename(salida_final)}:")
        print(resultado.stderr[-2500:])
        try:
            if os.path.exists(salida_final):
                os.remove(salida_final)
        except OSError:
            pass
        return False
    if not os.path.exists(salida_final) or os.path.getsize(salida_final) <= 0:
        print(f"  ERROR FFmpeg no produjo un archivo valido: {salida_final}")
        return False
    return True


def cortar_por_segmentos(video_path, segmentos_clip, salida_final, num_pistas):
    """Une varios segmentos narrativos en un solo clip usando NVENC."""
    normalizados = normalizar_segmentos_sin_duplicados(segmentos_clip)
    if normalizados != segmentos_clip:
        print("  ADVERTENCIA: segmentos duplicados/solapados detectados; se normalizan antes de NVENC.")
    segmentos_limpios = [(float(seg["inicio"]), float(seg["fin"])) for seg in normalizados]
    if not segmentos_limpios:
        return -1, []
    duracion_normalizada = sum(fin - inicio for inicio, fin in segmentos_limpios)
    if ((DURACION_MIN_CLIP and duracion_normalizada < DURACION_MIN_CLIP)
            or (DURACION_MAX_CLIP and duracion_normalizada > DURACION_MAX_CLIP)):
        print(f"  ERROR: segmentos normalizados duran {duracion_normalizada:.3f}s y no cumplen MIN/MAX.")
        return -1, []
    # Los segmentos compuestos ya expresan exactamente el material que se
    # debe conservar. No se aplica una segunda eliminación de silencios: eso
    # alteraría su duración contractual y rompería la verificación posterior.
    rangos_abs = [(float(s), float(e)) for s, e in segmentos_limpios]
    offset = rangos_abs[0][0]
    rangos_rel = [(round(s - offset, 3), round(e - offset, 3)) for s, e in rangos_abs]
    if not rangos_rel:
        return -1, rangos_abs
    filtro, mapas_salida = construir_filtro_multipista(rangos_rel, num_pistas)
    comando = ["ffmpeg", "-y", "-ss", str(offset), "-i", video_path, "-filter_complex", filtro]
    if rangos_abs[-1][1] - offset > 1000:
        # Un resumen puede saltar horas. Abrir cada tramo evita decodificar
        # todas las horas omitidas manteniendo la misma línea de edición.
        locales = [(0, round(e - s, 3)) for s, e in rangos_abs]
        # Reemplazo por ocurrencias separado para cada pista y video.
        filtro, mapas_salida = construir_filtro_multipista(locales, num_pistas)
        for pista in ["v"] + [f"a:{p}" for p in range(num_pistas)]:
            contador = iter(range(len(locales)))
            filtro = re.sub(re.escape(f"[0:{pista}]"), lambda m: f"[{next(contador)}:{pista}]", filtro)
        comando = ["ffmpeg", "-y"]
        for s, e in rangos_abs:
            comando += ["-threads", "1", "-ss", str(s), "-t", str(e-s), "-i", video_path]
        comando += ["-filter_complex", filtro]
    for m in mapas_salida:
        comando += ["-map", m]
    comando += _args_video_nvenc() + ["-map_metadata", "0", salida_final]
    ok = _ejecutar_ffmpeg(comando, salida_final)
    return (len(rangos_rel) - 1, rangos_abs) if ok else (-1, rangos_abs)

def cortar_con_silencios_removidos(video_path, inicio, fin, salida_final, num_pistas):
    """
    Recorta y elimina silencios en UNA sola ejecución de FFmpeg.

    Antes se hacía:
      1) encode CPU -> temporal
      2) filter_complex
      3) encode CPU -> final

    Ahora:
      1) filter_complex directamente desde el original
      2) un solo encode NVENC -> final

    Esto evita una codificación completa intermedia y mueve el encode de
    video a la RTX 4060.
    """
    rangos_abs = calcular_rangos_a_mantener(inicio, fin, todos_los_segmentos)

    # Los filtros se aplican directamente sobre el video original; por eso
    # estos timestamps deben mantenerse absolutos. Restar ``inicio`` aquí
    # hacía que un clip que empieza, por ejemplo, en 300s se renderizara
    # accidentalmente desde el segundo 0.
    rangos_render = [
        (round(s, 3), round(e, 3))
        for s, e in rangos_abs
        if (e - s) > 0.05
    ]

    if not rangos_render:
        return 0, rangos_abs

    # Caso simple: no hay silencios internos que eliminar.
    if len(rangos_render) == 1:
        s, e = rangos_render[0]
        comando = [
            "ffmpeg", "-y",
            "-ss", str(s),
            "-i", video_path,
            "-t", str(e - s),
            "-map", "0:v",
        ]
        for pista in range(num_pistas):
            comando += ["-map", f"0:a:{pista}"]

        comando += _args_video_nvenc()
        comando += ["-map_metadata", "0", salida_final]

        ok = _ejecutar_ffmpeg(comando, salida_final)
        return (0, rangos_abs) if ok else (-1, rangos_abs)

    # Caso con silencios: trim/concat directamente desde el original.
    filtro, mapas_salida = construir_filtro_multipista(rangos_render, num_pistas)

    comando = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-filter_complex", filtro,
    ]

    for m in mapas_salida:
        comando += ["-map", m]

    comando += _args_video_nvenc()
    comando += ["-map_metadata", "0", salida_final]

    ok = _ejecutar_ffmpeg(comando, salida_final)
    return (len(rangos_render) - 1, rangos_abs) if ok else (-1, rangos_abs)

usados = set()
registro_para_historial = []

for i, clip in enumerate(clips, start=1):
    segmentos_clip = clip.get("segmentos") or [{"inicio": clip.get("inicio"), "fin": clip.get("fin")}]
    inicio = clip.get("inicio")
    fin = clip.get("fin")
    if segmentos_clip and isinstance(segmentos_clip, list):
        try:
            inicio = float(segmentos_clip[0]["inicio"])
            fin = float(segmentos_clip[-1]["fin"])
        except (KeyError, TypeError, ValueError, IndexError):
            clip["error_render"] = "Segmentos inválidos"
            continue
    # Tope estricto: nunca se renderiza un clip por encima del maximo configurado.
    # Se aplica siempre sobre la lista de segmentos (si el clip no traia, ya se
    # construyo una a partir de inicio/fin).
    if DURACION_MAX_CLIP:
        originales = [(float(g["inicio"]), float(g["fin"])) for g in segmentos_clip]
        recortados = recortar_segmentos_a_maximo(originales, DURACION_MAX_CLIP)
        if not recortados:
            clip["error_render"] = "Sin material dentro del maximo de duracion"
            continue
        if recortados != originales:
            print(f"  AJUSTE: el clip {i} superaba {DURACION_MAX_CLIP}s; se recorta el final.")
            segmentos_clip = [{"inicio": a, "fin": b} for a, b in recortados]
            clip["segmentos"] = segmentos_clip
            inicio, fin = recortados[0][0], recortados[-1][1]
            clip["inicio"], clip["fin"] = inicio, fin
    titulo = clip.get("titulo", "clip")
    razon = clip.get("razon", "")

    nombre_base = nombre_archivo_seguro(titulo, i)
    nombre_final = nombre_base
    contador = 2
    while nombre_final in usados:
        nombre_final = f"{nombre_base}_{contador}"
        contador += 1
    usados.add(nombre_final)

    salida = os.path.join(carpeta_salida, f"{nombre_final}.mkv")

    print(f"Cortando clip {i}/{len(clips)}: {inicio}s - {fin}s | \"{titulo}\"")
    if segmentos_clip:
        huecos_quitados, rangos_abs = cortar_por_segmentos(video_path, segmentos_clip, salida, NUM_PISTAS_AUDIO)
        print(f"  -> Render narrativo por {len(segmentos_clip)} segmento(s).")
    else:
        huecos_quitados, rangos_abs = cortar_con_silencios_removidos(video_path, inicio, fin, salida, NUM_PISTAS_AUDIO)
    if huecos_quitados > 0:
        print(f"  -> {huecos_quitados} salto(s) entre segmentos seleccionados.")

    print(f"  -> Guardado con {NUM_PISTAS_AUDIO} pista(s) de audio separadas (.mkv), listo para quitar musica en tu editor.")

    # Verificacion de la duracion REAL del archivo (el contenedor suma unas
    # centesimas a lo planificado): si pasa del maximo se recorta o se descarta.
    if huecos_quitados >= 0 and DURACION_MAX_CLIP and os.path.exists(salida):
        ok_max, real = catalogo_clips.recortar_a_maximo(salida, DURACION_MAX_CLIP)
        if not ok_max:
            print(f"  ERROR: el clip dura {real:.2f}s (max {DURACION_MAX_CLIP}s) y no se pudo recortar; se elimina.")
            catalogo_clips.borrar_clip(salida)
            huecos_quitados = -1
        elif real and abs(real - sum(e - s for s, e in rangos_abs)) > 0.3:
            print(f"  AJUSTE: duracion real {real:.2f}s tras recortar al maximo.")

    # Guardamos la ruta exacta para que la verificación post-render no tenga
    # que adivinar el nombre del archivo generado.
    if huecos_quitados < 0 or not os.path.exists(salida) or os.path.getsize(salida) <= 0:
        clip.pop("archivo", None)
        clip.pop("ruta_archivo", None)
        clip["error_render"] = "FFmpeg no genero un archivo valido"
        print("  -> ERROR: no se persistira metadata de archivo inexistente.")
        continue
    clip["segmentos"] = [{"inicio": round(s, 3), "fin": round(e, 3)} for s, e in rangos_abs]
    clip["inicio"] = clip["segmentos"][0]["inicio"]
    clip["fin"] = clip["segmentos"][-1]["fin"]
    clip["duracion"] = round(sum(s["fin"] - s["inicio"] for s in clip["segmentos"]), 3)
    clip["duracion_final"] = clip["duracion"]
    if clip.get("duracion_original_arco"):
        clip["ratio_compresion"] = round(clip["duracion"] / clip["duracion_original_arco"], 3)
    clip["densidad_cambios"] = round((len(clip["segmentos"]) - 1) / clip["duracion"] * 5, 3)
    clip["puntos_corte"] = [{"tiempo": seg["inicio"], "motivo": "segmento_renderizado"} for seg in clip["segmentos"]] + [{"tiempo": clip["fin"], "motivo": "fin_renderizado"}]
    registrar_render(salida, video_path, clip["segmentos"])
    clip["archivo"] = str(salida)
    clip["ruta_archivo"] = str(salida)
    clip.pop("error_render", None)

    registro_para_historial.append({
        "titulo": titulo,
        "razon": razon,
        "archivo": f"{nombre_final}.mkv",
        "ruta_archivo": str(salida),
        "stream": nombre_video,
        "fecha_generado": datetime.now().strftime("%Y-%m-%d"),
        "registrado": False
    })

historial = []
if os.path.exists(ARCHIVO_HISTORIAL):
    with open(ARCHIVO_HISTORIAL, "r", encoding="utf-8") as f:
        historial = json.load(f)
historial.extend(registro_para_historial)
with open(ARCHIVO_HISTORIAL, "w", encoding="utf-8") as f:
    json.dump(historial, f, ensure_ascii=False, indent=2)

# Actualizar clips_sugeridos.json con las rutas reales generadas.
with open(os.path.join(CARPETA_RESULTADOS, "clips_sugeridos.json"), "w", encoding="utf-8") as f:
    json.dump(clips, f, ensure_ascii=False, indent=2)
guardar_identidad_artefacto(os.path.join(CARPETA_RESULTADOS, "clips_sugeridos.json"), video_path, "clips_sugeridos")

# Catalogo acumulado: permite validar los clips de TODOS los streams procesados.
try:
    catalogo_clips.registrar_clips(
        CARPETA_RESULTADOS, [c for c in clips if c.get("ruta_archivo")],
        fuente=exigir_identidad_artefacto(os.path.join(CARPETA_RESULTADOS, "clips_sugeridos.json"), video_path, "clips_sugeridos"),
        stream=nombre_video,
        contexto_juego=catalogo_clips.leer_contexto_juego(CARPETA_RESULTADOS),
    )
except Exception as exc:
    print(f"ADVERTENCIA: no se pudo actualizar el catalogo de clips: {exc}")

print(f"\nListo. {len(registro_para_historial)}/{len(clips)} clips guardados en: {carpeta_salida}")

# --- Clip de "mejores momentos" / resumen, si existe el plan ---
resumen_error = False
if os.path.exists(os.path.join(CARPETA_RESULTADOS, "resumen_plan.json")):
    exigir_identidad_artefacto(os.path.join(CARPETA_RESULTADOS, "resumen_plan.json"), video_path, "resumen_plan")
    with open(os.path.join(CARPETA_RESULTADOS, "resumen_plan.json"), "r", encoding="utf-8") as f:
        resumen_plan = json.load(f)

    titulo_resumen = resumen_plan.get("titulo", "mejores momentos")
    momentos_resumen = resumen_plan.get("momentos", [])

    if momentos_resumen:
        print(f"\nArmando clip de resumen: \"{titulo_resumen}\" ({len(momentos_resumen)} momentos)...")

        nombre_resumen = nombre_archivo_seguro(titulo_resumen, 0).replace("00_", "00_resumen_")
        salida_resumen = os.path.join(carpeta_salida, f"{nombre_resumen}.mkv")

        momentos_limpios = normalizar_segmentos_sin_duplicados(momentos_resumen)
        if momentos_limpios != momentos_resumen:
            print("  ADVERTENCIA: momentos repetidos/solapados en resumen; se normalizan antes de renderizar.")
        if DURACION_MAX_CLIP:
            ajustados = recortar_segmentos_a_maximo([(float(m["inicio"]), float(m["fin"])) for m in momentos_limpios], DURACION_MAX_CLIP)
            if ajustados != [(float(m["inicio"]), float(m["fin"])) for m in momentos_limpios]:
                print(f"  AJUSTE: el resumen superaba {DURACION_MAX_CLIP}s; se recorta el final.")
            momentos_limpios = [{"inicio": a, "fin": b} for a, b in ajustados]

        resultado, rangos = cortar_por_segmentos(video_path, momentos_limpios, salida_resumen, NUM_PISTAS_AUDIO)
        if resultado >= 0:
            resumen_plan["momentos"] = momentos_limpios
            resumen_plan["duracion"] = round(sum(e - i for i, e in rangos), 3)
            resumen_plan["archivo"] = salida_resumen
            resumen_plan.pop("error_render", None)
            registrar_render(salida_resumen, video_path, [{"inicio": i, "fin": e} for i, e in rangos])
            with open(os.path.join(CARPETA_RESULTADOS, "resumen_plan.json"), "w", encoding="utf-8") as f:
                json.dump(resumen_plan, f, ensure_ascii=False, indent=2)
            print(f"Listo. Clip de resumen guardado: {salida_resumen}")
        else:
            resumen_error = True
            resumen_plan.pop("archivo", None)
            resumen_plan.pop("ruta_archivo", None)
            resumen_plan["error_render"] = "Resumen normalizado inválido o fallo de FFmpeg"
            with open(os.path.join(CARPETA_RESULTADOS, "resumen_plan.json"), "w", encoding="utf-8") as f:
                json.dump(resumen_plan, f, ensure_ascii=False, indent=2)
            print("ERROR: resumen rechazado; no se declara render correcto.")
    else:
        print("\nEl plan de resumen no tenía momentos, se omite.")
else:
    print("\nNo hay plan de resumen para este stream.")

if resumen_error or any(c.get("error_render") for c in clips):
    raise SystemExit(1)

# --- Borrado del stream original ---
if MODO_AUTOMATICO:
    print("\n(Modo automatico: el borrado del original, si aplica, lo maneja quien llamo a este script)")
else:
    respuesta = input(f"\n¿Borrar el stream original ({os.path.basename(video_path)})? Ya tienes los clips generados. (s/n): ").strip().lower()
    if respuesta == "s":
        try:
            os.remove(video_path)
            print(f"Borrado: {video_path}")
        except OSError as e:
            print(f"No se pudo borrar el archivo: {e}")
    else:
        print("Se conserva el archivo original.")
