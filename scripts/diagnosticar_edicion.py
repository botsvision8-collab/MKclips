"""Diagnóstico de un render que falla: prueba la edición por partes (a baja resolución) y dice cuál rompe FFmpeg.

Uso:  python diagnosticar_edicion.py "C:\\ruta\\al\\clip.mkv"
Escribe el resultado en pantalla y en ``diagnostico_edicion.txt`` junto al clip. No modifica nada."""
from __future__ import annotations

import copy
import os
import subprocess
import sys
import tempfile
import time

try:
    from . import editor_modelo as modelo, editor_fuentes as fuentes, editor_piezas as piezas_mod, editor_render_piezas as rp, editor_render as render
except ImportError:
    import editor_render as render
    import editor_modelo as modelo
    import editor_fuentes as fuentes
    import editor_piezas as piezas_mod
    import editor_render_piezas as rp

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _reducir(edicion, divisor=4):
    e = copy.deepcopy(edicion)
    e["salida"]["ancho"] = max(2, int(e["salida"]["ancho"] / divisor) // 2 * 2)
    e["salida"]["alto"] = max(2, int(e["salida"]["alto"] / divisor) // 2 * 2)
    return e


def _probar(edicion, trabajo, mapas_usar=("v", "a"), sin_texto=False, plano=False):
    """Devuelve (ok, texto de error)."""
    plan = rp.planificar(edicion, {}, audio_plano=plano)
    filtro = plan["filtro"].replace("\n", "")
    if sin_texto and "ass=subs.ass:fontsdir=fuentes" in filtro:
        filtro = filtro.replace("ass=subs.ass:fontsdir=fuentes", "null")
    mapas = [m for m in plan["mapas"] if (m == "[vout]" and "v" in mapas_usar) or (m != "[vout]" and "a" in mapas_usar)]
    if not mapas:
        return True, ""
    if len(mapas_usar) == 1:           # se corta el grafo para que no queden salidas sin conectar
        es_audio = lambda seg: any(k in seg for k in ("anullsrc", "aformat", "amix", "aresample", "a=1"))
        filtro = ";".join(seg for seg in filtro.split(";") if es_audio(seg) == (mapas_usar[0] == "a"))
    comando = ["ffmpeg", "-y", "-v", "error", "-nostats"] + plan["entradas"] + ["-filter_complex", filtro]
    for m in mapas:
        comando += ["-map", m]
    comando += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", f"{plan['total']:.3f}", "-f", "null", "-"]
    r = subprocess.run(comando, cwd=trabajo, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=_SIN_VENTANA)
    return r.returncode == 0, (r.stderr or "")[-600:]


def diagnosticar(ruta_clip, salida=print):
    edicion = modelo.cargar_edicion(ruta_clip)
    if not edicion:
        salida("No hay una edición guardada para este archivo. Arrastra el clip ORIGINAL (el que abres en el editor), no el video ya renderizado.")
        return
    if not piezas_mod.tiene_piezas(edicion):
        salida("Esta edición no usa piezas; no hace falta este diagnóstico.")
        return
    e0 = _reducir(edicion)
    lineas = []

    def decir(t):
        lineas.append(t)
        salida(t)

    with tempfile.TemporaryDirectory(prefix="mkclips_diag_") as trabajo:
        with open(os.path.join(trabajo, "subs.ass"), "w", encoding="utf-8") as f:
            f.write(piezas_mod.generar_ass(e0))
        os.makedirs(os.path.join(trabajo, "fuentes"), exist_ok=True)
        for familia in dict.fromkeys(piezas_mod.familias_de_texto(e0)):
            try:
                fuentes.preparar_carpeta_fuentes(familia, os.path.join(trabajo, "fuentes"))
            except Exception as ex:
                decir(f"(aviso) no se pudo preparar la fuente «{familia}»: {ex}")

        decir(f"Diagnóstico de {ruta_clip}")
        decir("\nAudio de cada pieza (volumen máximo: cerca de 0 dB = suena fuerte; -inf o muy bajo = mudo):")
        for p in e0["piezas"]:
            if p["tipo"] != "audio":
                continue
            archivo = ruta_clip if p["fuente"] == "clip" else p["archivo"]
            try:
                r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name,channels,sample_rate,channel_layout",
                                    "-of", "csv=p=0", archivo], capture_output=True, text=True, timeout=30, creationflags=_SIN_VENTANA)
                info = r.stdout.strip().replace("\n", " | ") or "SIN PISTA DE AUDIO"
            except Exception as ex:
                info = f"no se pudo leer ({ex})"
            n_pistas = len([x for x in info.split(" | ") if x and not x.startswith("SIN")])
            niveles = []
            for i in range(max(1, n_pistas)):
                opciones = ["-ss", f"{p['desde']:.3f}", "-t", f"{min(p['dur'], 10):.3f}"]
                mx = render._volumen_max(archivo, opciones, pista=i, seek_salida=p.get("fuente") == "clip") if n_pistas else None
                niveles.append("no se pudo medir" if mx is None else ("mudo" if mx < -60 else f"{mx:.1f} dB"))
            decir(f"  {p['carril']} {p.get('nombre') or p['id']}: {info} · volumen por pista de audio: {', '.join(niveles)}")
        pruebas = [("Edición completa (baja resolución)", e0, ("v", "a"), False),
                   ("Solo vídeo", e0, ("v",), False),
                   ("Solo audio", e0, ("a",), False),
                   ("Vídeo sin textos", e0, ("v",), True)]
        fallo = False
        ok_plano, err_plano = _probar(e0, trabajo, ("a",), False, True)
        for nombre, e, mapas, sin in pruebas:
            t = time.time()
            ok, err = _probar(e, trabajo, mapas, sin)
            fallo = fallo or not ok
            decir(f"[{'OK ' if ok else 'FALLA'}] {nombre} ({time.time() - t:.0f} s)" + ("" if ok else "\n      " + err.strip().replace("\n", "\n      ")))
        decir(f"[{'OK ' if ok_plano else 'FALLA'}] Solo audio (montaje alternativo)" + ("" if ok_plano else "\n      " + err_plano.strip().replace("\n", "\n      ")))
        if not fallo:
            decir("\nA baja resolución no falla. Pruebo con la resolución real (puede tardar):")
            t = time.time()
            ok, err = _probar(edicion, trabajo)
            decir(f"[{'OK ' if ok else 'FALLA'}] Edición completa (resolución real) ({time.time() - t:.0f} s)" + ("" if ok else "\n      " + err.strip().replace("\n", "\n      ")))
            decir("Si también pasa, el fallo no viene de la edición sino del equipo en ese momento (memoria, GPU/NVENC, disco)." if ok else
                  "Falla solo a resolución real: suele ser memoria o un límite de la GPU con tantas capas.")
        else:
            # quitar cada pieza que no es del clip, de una en una
            decir("\nQuitando piezas una a una (si una prueba pasa a OK, esa pieza es la culpable):")
            for p in e0["piezas"]:
                if p["fuente"] == "clip":
                    continue
                e = copy.deepcopy(e0)
                quitar = {p["id"]} | {q["id"] for q in e["piezas"] if p.get("enlace") and q.get("enlace") == p["enlace"]}
                e["piezas"] = [q for q in e["piezas"] if q["id"] not in quitar]
                ok, err = _probar(e, trabajo)
                nombre = f"{p['carril']} · {p['tipo']} · {p.get('nombre') or p['id']} (t={p['t']:.1f}, dur={p['dur']:.1f})"
                decir(f"  sin «{nombre}»: {'OK  <-- sin esta pieza funciona' if ok else 'sigue fallando'}")
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(ruta_clip)), "diagnostico_edicion.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lineas))
    except OSError:
        pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Uso: python diagnosticar_edicion.py "ruta\\del\\clip.mkv"')
        sys.exit(1)
    diagnosticar(sys.argv[1])
