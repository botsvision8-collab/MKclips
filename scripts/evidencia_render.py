"""Contrato de render: vincula fuente, segmentos finales y bytes del MKV."""
import hashlib
import json
from pathlib import Path
import subprocess

from cache_mkclips import identidad_fuente


def comprobar_correspondencia(archivo, segmentos, video):
    """Muestreo físico independiente del manifiesto, tres puntos por tramo.

    No sustituye la reproducción humana: escenas estáticas pueden ser ambiguas.
    """
    import numpy as np
    fps, ancho, alto = 30, 64, 36
    def frames(ruta, inicio, duracion):
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(inicio), "-i", str(ruta),
                            "-t", str(duracion), "-vf", f"fps={fps},scale={ancho}:{alto},format=gray",
                            "-f", "rawvideo", "-"], capture_output=True, timeout=300)
        if r.returncode or not r.stdout:
            raise ValueError("No se pudo obtener muestreo visual de " + str(ruta))
        return np.frombuffer(r.stdout, dtype=np.uint8).reshape(-1, alto * ancho).astype(np.float32)
    origen = segmentos[0]["inicio"]
    span = segmentos[-1]["fin"] - origen
    fuente = frames(video, origen, span) if span <= 1000 else None
    duracion = sum(s["fin"] - s["inicio"] for s in segmentos)
    salida = frames(archivo, 0, duracion)
    cursor, pruebas = 0., []
    for numero, seg in enumerate(segmentos, 1):
        largo = seg["fin"] - seg["inicio"]
        fotogramas = fuente if fuente is not None else frames(video, seg["inicio"], largo)
        base = origen if fuente is not None else seg["inicio"]
        errores = []
        for fraccion in (.25, .5, .75):
            t = largo * fraccion
            idx = min(len(salida) - 1, max(0, int((cursor + t) * fps)))
            esperado = round((seg["inicio"] - base + idx / fps - cursor) * fps)
            vecinos = fotogramas[max(0, esperado - 7):min(len(fotogramas), esperado + 8)]
            if not len(vecinos): raise ValueError("Muestra fuera de la fuente")
            errores.append(float(np.abs(vecinos - salida[idx]).mean(axis=1).min()))
        pruebas.append({"segmento": numero, "error_visual_medio": round(sum(errores) / len(errores), 3)})
        cursor += largo
    incorrectos = [p for p in pruebas if p["error_visual_medio"] > 18]
    if incorrectos:
        raise ValueError("La imagen renderizada no coincide con la fuente en segmentos: " + str(incorrectos))
    return {"metodo": "3 muestras por segmento, gris 64x36, 30fps; tolerancia temporal 0.25s; MAE máximo 18",
            "segmentos": pruebas, "alcance": "Muestreo visual; narrativa, audio y sincronía requieren valoración humana"}


def sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""): h.update(bloque)
    return h.hexdigest()


def registrar_render(archivo, fuente, segmentos):
    datos = {"version": 1, "fuente": identidad_fuente(fuente), "segmentos": segmentos,
             "sha256": sha256(archivo), "archivo": str(Path(archivo).resolve())}
    Path(str(archivo) + ".render.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return datos


def decodificar_completo(archivo, timeout=300):
    # El muxer null cuantiza timestamps al fps y da falsos "non monotonically increasing dts"
    # en clips con segmentos muy cortos; "drop" lo evita sin ocultar corrupción real.
    base = ["ffmpeg", "-v", "error", "-xerror", "-i", str(archivo), "-map", "0:v", "-map", "0:a?"]
    ultimo = None
    for opcion in (["-fps_mode", "drop"], ["-vsync", "drop"]):
        r = subprocess.run(base + opcion + ["-f", "null", "-"], capture_output=True, timeout=timeout)
        texto = r.stderr.decode(errors="replace")
        if "Unrecognized option" in texto or "not found" in texto:
            ultimo = r
            continue
        return r
    return ultimo


def verificar_render(archivo, segmentos, fuente):
    ruta = Path(str(archivo) + ".render.json")
    if not ruta.is_file():
        raise ValueError("Falta manifiesto del nuevo render; un archivo histórico no demuestra este contrato")
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    if datos.get("segmentos") != segmentos or datos.get("fuente") != fuente:
        raise ValueError("El render no corresponde a los segmentos/fuente declarados")
    if datos.get("sha256") != sha256(archivo):
        raise ValueError("El archivo cambió después del render")
    def pistas(ruta):
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(ruta)], capture_output=True, text=True, check=True)
        tipos = [s["codec_type"] for s in json.loads(r.stdout)["streams"]]
        return {t: tipos.count(t) for t in ("video", "audio")}
    pistas_salida = pistas(archivo)
    if pistas_salida != pistas(fuente["ruta_normalizada"]):
        raise ValueError("El número de pistas de video/audio difiere de la fuente")
    r = decodificar_completo(archivo)
    if r.returncode or r.stderr.strip():
        raise ValueError("Fallo de integridad al decodificar video/audio: " + r.stderr.decode(errors="replace")[-500:])
    return {"manifiesto": "CORRECTO", "sha256": datos["sha256"], "pistas": pistas_salida, "decodificacion_completa": "CORRECTO"}
