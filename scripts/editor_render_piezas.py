# -*- coding: utf-8 -*-
"""Render de la edición por piezas (línea de tiempo estilo DaVinci) con FFmpeg.

Cada pieza de video/imagen/audio es una entrada propia de FFmpeg (con ``-ss`` y ``-t``), así que mover o reordenar
trozos del clip no obliga a guardar en memoria lo que queda entre medias. El video se compone sobre un fondo negro
poniendo cada pieza en su instante (de la pista más baja a la más alta); el audio se arma pista por pista (huecos de
silencio entre piezas) y se mezcla. Los textos y los subtítulos se dibujan al final con un único archivo ASS.
"""
from __future__ import annotations
SELLO = "2026-10-23-c"        # lo muestra el editor para comprobar que todos los archivos están actualizados

import os
import re
import subprocess

try:
    from . import editor_modelo as modelo, editor_piezas as P, editor_render as R
except ImportError:  # módulo suelto desde scripts/
    import editor_modelo as modelo
    import editor_piezas as P
    import editor_render as R

MAX_ENTRADAS = 150
_CANALES = {}


def _f(n):
    return R._f(n)


def _canales_pista(ruta, pista):
    clave = (ruta, pista)
    if clave not in _CANALES:
        try:
            r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", f"a:{pista}", "-show_entries", "stream=channels", "-of", "csv=p=0", ruta],
                               capture_output=True, text=True, timeout=30, creationflags=R._SIN_VENTANA)
            _CANALES[clave] = int(r.stdout.strip().split(",")[0])
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            _CANALES[clave] = 2
    return _CANALES[clave]


def _renombrar(parte, pref):
    """Antepone ``pref`` a las etiquetas ``[nombre]`` de un fragmento de filtro (las entradas ``[3:v]`` no se tocan)."""
    return re.sub(r"\[([A-Za-z_][A-Za-z0-9_]*)\]", lambda m: f"[{pref}{m.group(1)}]", parte)


# ----------------------------------------------------------------------------- planificación
def piezas_activas(edicion):
    """Piezas que entran en el render: su pista no está oculta/silenciada, el archivo existe y caen dentro de la salida.

    Cada una lleva ``archivo`` (el clip o el medio), ``ext`` (segundos extra que se mantiene visible para una transición
    de la pieza siguiente) y se ordena de la pista más baja a la más alta."""
    piezas = edicion["piezas"]
    total = P.duracion_total(piezas)
    pistas = edicion.get("pistas") or {}
    ocultas, mudas = set(pistas.get("ocultas", [])), set(pistas.get("silenciadas", []))
    por_carril = {}
    for p in piezas:
        por_carril.setdefault(p["carril"], []).append(p)
    for lista in por_carril.values():
        lista.sort(key=lambda p: p["t"])
    resultado = []
    for p in sorted(piezas, key=lambda p: (P.numero(p["carril"]), p["t"])):
        if p["tipo"] == "texto" or p["t"] >= total - 0.02:
            continue
        if p["tipo"] == "audio":
            if p["carril"] in mudas or (p["volumen"] <= 0 and not (p.get("kf") or {}).get("volumen")):
                continue
        elif p["carril"] in ocultas:
            continue
        archivo = edicion["clip"] if P.es_clip(p) else p["archivo"]
        if not os.path.isfile(archivo):
            continue
        x = dict(p)
        x["archivo"] = archivo
        x["ext"] = 0.0
        if p["tipo"] != "audio":
            lista = por_carril[p["carril"]]
            i = next((k for k, q in enumerate(lista) if q["id"] == p["id"]), -1)
            sig = lista[i + 1] if 0 <= i < len(lista) - 1 else None
            if sig and sig["trans_in"]["tipo"] != "ninguna" and abs(sig["t"] - P.fin_de(p)) < 0.05 and sig["tipo"] != "audio":
                x["ext"] = round(sig["trans_in"]["dur"], 3)
        resultado.append(x)
    return resultado


def _cadena_audio(a, k, pista, canales):
    kf = a.get("kf") or {}
    cad = f"[{k}:a:{pista}]aresample=48000,{R._a_estereo(canales)},aformat=sample_fmts=fltp"
    if P.es_clip(a):
        cad += f",atrim=start={_f(a['desde'])}:duration={_f(P.consumo(a))},asetpts=PTS-STARTPTS"
    cad += R._atempo(a["velocidad"])
    if kf.get("volumen"):
        cad += f",volume=eval=frame:volume='{P.expr_kf(kf['volumen'])}'"
    else:
        cad += f",volume={_f(a['volumen'])}"
    if a["fundido_in"] > 0:
        cad += f",afade=t=in:st=0:d={_f(a['fundido_in'])}"
    if a["fundido_out"] > 0:
        cad += f",afade=t=out:st={_f(max(0.0, a['dur'] - a['fundido_out']))}:d={_f(a['fundido_out'])}"
    return cad


def _audio_plano(partes, mapas, activos, indice, s, total, formato, norm, nuevo, audio_wav=None):
    """Modo alternativo del audio: cada trozo se retrasa a su sitio con ``adelay`` y todos se suman con un único ``amix``
    (sin ``concat``). Se usa como reintento si el montaje normal falla con ciertos archivos."""
    etiquetas = []
    for a in sorted((x for x in activos if x["tipo"] == "audio" and (P.es_clip(x) or s == 0)), key=lambda q: q["t"]):
        pista = s if P.es_clip(a) else 0
        cad = _cadena_audio(a, indice[a["id"]], pista, 2 if a["id"] in (audio_wav or {}) else _canales_pista(a["archivo"], pista))
        ms = int(round(a["t"] * 1000))
        cad += f",atrim=end={_f(a['dur'])},asetpts=PTS-STARTPTS,{formato}" + (f",adelay={ms}|{ms}" if ms > 0 else "")
        e = nuevo("q")
        partes.append(cad + f"[{e}]")
        etiquetas.append(e)
    salida = f"a{s}out"
    if not etiquetas:
        partes.append(f"anullsrc=r=48000:cl=stereo:d={_f(total)},{formato}[{salida}]")
    else:
        base = nuevo("b")
        partes.append(f"anullsrc=r=48000:cl=stereo:d={_f(total)},{formato}[{base}]")
        n = len(etiquetas) + 1
        compensa = "" if norm else f",volume={n}"
        partes.append(f"[{base}]" + "".join(f"[{x}]" for x in etiquetas) +
                      f"amix=inputs={n}:duration=first:dropout_transition=0{norm}{compensa},atrim=end={_f(total)},asetpts=PTS-STARTPTS[{salida}]")
    mapas.append(f"[{salida}]")


def planificar(edicion, ia_listas=None, audio_plano=False, audio_wav=None, solo_audio=False):
    """Entradas de FFmpeg y filtro del render. Devuelve {"entradas": [argumentos], "filtro", "mapas", "total", "n_entradas"}."""
    ia_listas = ia_listas or {}
    audio_wav = audio_wav or {}          # id de pieza de audio -> WAV limpio ya recortado (extraído aparte del archivo original)
    piezas = edicion["piezas"]
    total = P.duracion_total(piezas)
    origen, salida = edicion["origen"], edicion["salida"]
    ow, oh = salida["ancho"], salida["alto"]
    fps = min(60.0, max(24.0, round(origen.get("fps", 30.0))))
    activos = piezas_activas(edicion)
    entradas, indice = [], {}
    n_streams = origen["pistas_audio"] if origen["pistas_audio"] >= 1 else (1 if any(a["tipo"] == "audio" and not P.es_clip(a) for a in activos) else 0)

    for a in activos:
        ruta = os.path.abspath(a["archivo"])
        if a["tipo"] == "imagen":
            entradas.append(["-loop", "1", "-framerate", "30", "-t", _f(a["dur"] + a["ext"] + 0.1), "-i", ruta])
        elif a["tipo"] == "audio" and a["id"] in audio_wav:
            entradas.append(["-t", _f(P.consumo(a) + 0.1), "-i", os.path.abspath(audio_wav[a["id"]])])
        elif a["tipo"] == "audio" and P.es_clip(a) and audio_plano:
            # Los cortes del audio del clip se hacen en el filtro: input-seek
            # puede dar silencio en ciertos MKV y output-seek en listas de
            # entradas queda ligado a la siguiente entrada.
            entradas.append(["-i", ruta])
        elif a["tipo"] == "audio" and P.es_clip(a):
            # No usar input-seek en el clip: ciertos MKV devuelven silencio.
            # El filtro de audio aplica atrim al offset exacto de cada pieza.
            entradas.append(["-i", ruta])
        else:
            entradas.append(["-ss", _f(a["desde"]), "-t", _f(P.consumo(a) + 0.05), "-i", ruta])
        indice[a["id"]] = len(entradas) - 1
    # mejora con IA: una entrada por trozo del clip y zona mejorada, ya cortada con -ss/-t
    ia_por_pieza = {}
    if ia_listas:
        for item in P.piezas_para_ia(piezas):
            p = item["pieza"]
            if p["id"] not in indice:
                continue
            mapa = {}
            for clave, ruta in ia_listas.items():
                entradas.append(["-ss", _f(item["offset"]), "-t", _f(p["dur"] + 0.05), "-i", os.path.abspath(ruta)])
                mapa[clave] = len(entradas) - 1
            ia_por_pieza[p["id"]] = mapa
    if len(entradas) > MAX_ENTRADAS:
        raise RuntimeError(f"Hay demasiadas piezas en la línea de tiempo ({len(entradas)}). Quita o une algunas antes de renderizar.")

    partes = [f"color=c=black:s={ow}x{oh}:r={_f(fps)}:d={_f(total)},format=yuv420p[base]"]
    ultimo = "base"
    capas = [a for a in activos if a["tipo"] in ("video", "imagen")]
    for n, a in enumerate(capas):
        k = indice[a["id"]]
        pref = f"p{k}_"
        t0, t1 = a["t"], a["t"] + a["dur"] + a["ext"]
        vel = a["velocidad"] if a["tipo"] == "video" else 1.0
        veloz = f",setpts=(PTS-STARTPTS)/{_f(vel)}" if abs(vel - 1.0) > 1e-4 else ",setpts=PTS-STARTPTS"
        rx = ry = 0
        completa = True
        propia_medio = (not P.es_clip(a)) and a["tipo"] == "video" and bool(a.get("encuadre")) and a["ancho"] > 0 and a["alto"] > 0
        if P.es_clip(a) or propia_medio:
            enc = a.get("encuadre") or edicion["encuadre"]
            mej = ia_por_pieza.get(a["id"], {}) if ("encuadre" not in a and not propia_medio) else {}
            dw, dh = (a["ancho"], a["alto"]) if propia_medio else (origen["ancho"], origen["alto"])
            cadena = [f"[{k}:v]{'fps=30,' if propia_medio else ''}{veloz[1:]}[vc]"]
            kf = a.get("kf") or {}
            if enc.get("modo") == "recorte" and any(kf.get(q) for q in ("rec_x","rec_y","rec_w","rec_h")):
                base=enc["recorte"]; vals={"rec_x":base["x"],"rec_y":base["y"],"rec_w":base["w"],"rec_h":base["h"]}
                for q in vals:
                    if kf.get(q): vals[q]=P.expr_kf(kf[q])
                x, y, w, h = (vals[q] for q in ("rec_x", "rec_y", "rec_w", "rec_h"))
                # Mismo cálculo que la vista previa (rectAspecto): se conserva el centro y se ajusta a la proporción de la salida, sin deformar.
                # Las variables intermedias van con st()/ld() para que la expresión no crezca.
                asp = ow / oh
                pre = (f"st(0,({w})*{dw});st(1,({h})*{dh});st(2,if(gt(ld(0)/ld(1),{asp:.6f}),ld(1)*{asp:.6f},ld(0)));st(3,ld(2)/{asp:.6f});"
                       f"st(4,min(1,min({dw}/ld(2),{dh}/ld(3))));st(2,ld(2)*ld(4));st(3,ld(3)*ld(4));"
                       f"st(5,min(max(0,(({x})+({w})/2)*{dw}-ld(2)/2),{dw}-ld(2)));st(6,min(max(0,(({y})+({h})/2)*{dh}-ld(3)/2),{dh}-ld(3)));st(7,{ow}/ld(2));")
                cadena += [f"[vc]scale=w='{pre}trunc({dw}*ld(7)/2)*2':h='{pre}trunc({dh}*ld(7)/2)*2':eval=frame:flags=lanczos,"
                           f"crop={ow}:{oh}:x='{pre}ld(5)*ld(7)':y='{pre}ld(6)*ld(7)',setsar=1[vl]"]
            else: cadena += R._cadenas_encuadre(enc, dw, dh, ow, oh, mej)
            partes.extend(_renombrar(c, pref) for c in cadena)
            capa = f"{pref}vl"
        else:
            if a["modo"] == "recuadro":
                rw = max(2, int(round(a["recuadro"]["w"] * ow / 2)) * 2)
                rx, ry = int(round(a["recuadro"]["x"] * ow)), int(round(a["recuadro"]["y"] * oh))
                ajuste = f"scale={rw}:-2:flags=lanczos"
                completa = False
            else:
                ajuste = f"scale={ow}:{oh}:force_original_aspect_ratio=increase:flags=lanczos,crop={ow}:{oh}"
            partes.append(f"[{k}:v]fps=30,{ajuste},setsar=1{veloz}[{pref}vl]")
            capa = f"{pref}vl"
        cadena = []
        kf = a.get("kf") or {}
        bordes=a.get("recorte_bordes") or {}
        iz, de, ar, ab=(float(bordes.get(k,0)) for k in ("izquierda","derecha","arriba","abajo"))
        if iz+de+ar+ab>0.0001:
            if completa: cadena += [f"crop=w='iw*{_f(1-iz-de)}':h='ih*{_f(1-ar-ab)}':x='iw*{_f(iz)}':y='ih*{_f(ar)}'", f"scale={ow}:{oh}:flags=lanczos"]
            else:
                rw=max(2,int(round(a["recuadro"]["w"]*ow/2))*2);rh=max(2,int(round(rw*a["alto"]/max(1,a["ancho"]))));cadena += [f"crop=w='iw*{_f(1-iz-de)}':h='ih*{_f(1-ar-ab)}':x='iw*{_f(iz)}':y='ih*{_f(ar)}'",f"scale={rw}:{rh}:flags=lanczos"]
        if a.get("flip_h"): cadena.append("hflip")
        if a.get("flip_v"): cadena.append("vflip")
        rot=P.expr_kf(kf["rotacion"]) if kf.get("rotacion") else _f(a.get("rotacion",0))
        if kf.get("rotacion") or abs(float(a.get("rotacion",0)))>0.001:
            cadena += ["format=yuva420p",f"rotate=angle='({rot})*PI/180':ow=iw:oh=ih:c=none:bilinear=1"]
        # zoom y posición (con o sin keyframes)
        if completa and (a["zoom"] > 1.001 or kf.get("zoom") or kf.get("pos_x") or kf.get("pos_y") or abs(a["pos_x"]) > 1e-3 or abs(a["pos_y"]) > 1e-3):
            z = P.expr_kf(kf["zoom"]) if kf.get("zoom") else _f(a["zoom"])
            px = P.expr_kf(kf["pos_x"]) if kf.get("pos_x") else _f(a["pos_x"])
            py = P.expr_kf(kf["pos_y"]) if kf.get("pos_y") else _f(a["pos_y"])
            if kf.get("zoom"):
                cadena.append(f"scale=w='trunc({ow}*({z})/2)*2':h='trunc({oh}*({z})/2)*2':eval=frame:flags=bicubic")
            else:
                cadena.append(f"scale={max(ow, int(round(ow * a['zoom'] / 2)) * 2)}:{max(oh, int(round(oh * a['zoom'] / 2)) * 2)}:flags=bicubic")
            if kf.get("zoom"):       # el tamaño cambia en cada fotograma: el desplazamiento se calcula con la fórmula del zoom, no con iw/ih (que no se actualizan)
                cadena.append(f"crop={ow}:{oh}:x='(trunc({ow}*({z})/2)*2-{ow})/2*(1+({px}))':y='(trunc({oh}*({z})/2)*2-{oh})/2*(1+({py}))'")
            else:
                cadena.append(f"crop={ow}:{oh}:x='(iw-{ow})/2*(1+({px}))':y='(ih-{oh})/2*(1+({py}))'")
        tr = a["trans_in"]
        necesita_alfa = (a["opacidad"] < 0.999 or kf.get("opacidad") or a["fundido_in"] > 0 or a["fundido_out"] > 0 or tr["tipo"] == "disolver")
        if necesita_alfa:
            cadena.append("format=yuva420p")
            if kf.get("opacidad"):
                cadena.append(f"geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='alpha(X,Y)*({P.expr_kf(kf['opacidad'], var='T')})'")
            elif a["opacidad"] < 0.999:
                cadena.append(f"colorchannelmixer=aa={_f(a['opacidad'])}")
            entrada = max(a["fundido_in"], tr["dur"] if tr["tipo"] == "disolver" else 0.0)
            if entrada > 0:
                cadena.append(f"fade=t=in:st=0:d={_f(entrada)}:alpha=1")
            if a["fundido_out"] > 0:
                cadena.append(f"fade=t=out:st={_f(max(0.0, a['dur'] - a['fundido_out']))}:d={_f(a['fundido_out'])}:alpha=1")
        if a["ext"] > 0.01:
            cadena.append(f"tpad=stop_mode=clone:stop_duration={_f(a['ext'])}")
        cadena.append(f"setpts=PTS-STARTPTS+{_f(t0)}/TB")
        partes.append(f"[{capa}]" + ",".join(cadena) + f"[{pref}ov]")
        ox, oy = f"{rx}+({_f(a.get('tras_x',0))})*{ow}", f"{ry}+({_f(a.get('tras_y',0))})*{oh}"
        d = tr["dur"]
        if tr["tipo"].startswith("deslizar") and completa:
            avance = f"min(1,max(0,(t-{_f(t0)})/{_f(d)}))"
            if tr["tipo"] == "deslizar_izq":
                ox = f"-{ow}*(1-{avance})"
            elif tr["tipo"] == "deslizar_der":
                ox = f"{ow}*(1-{avance})"
            elif tr["tipo"] == "deslizar_arriba":
                oy = f"-{oh}*(1-{avance})"
            else:
                oy = f"{oh}*(1-{avance})"
        sig = f"m{n}"
        partes.append(f"[{ultimo}][{pref}ov]overlay=x='{ox}':y='{oy}':eof_action=pass:enable='between(t,{_f(t0)},{_f(t1)})'[{sig}]")
        ultimo = sig
    con_ass = bool((edicion["subtitulos"]["activos"] and edicion["subtitulos"]["lineas"]) or P.textos_activos(edicion))
    if con_ass:
        partes.append(f"[{ultimo}]ass=subs.ass:fontsdir=fuentes[vout]")
    else:
        partes.append(f"[{ultimo}]null[vout]")
    mapas = ["[vout]"]
    # ------------------------------------------------------------------ audio
    norm = ":normalize=0" if R.amix_tiene_normalize() else ""
    formato = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
    contador = [0]
    inicio_audio = len(partes)

    def nuevo(prefijo):
        contador[0] += 1
        return f"{prefijo}{contador[0]}"

    for s in range(n_streams):
        if audio_plano:
            _audio_plano(partes, mapas, activos, indice, s, total, formato, norm, nuevo, audio_wav)
            continue
        carriles = {}
        for a in activos:
            if a["tipo"] != "audio":
                continue
            if P.es_clip(a) or s == 0:
                carriles.setdefault(a["carril"], []).append(a)
        etiquetas_carril = []
        for carril in sorted(carriles, key=P.numero):
            lista = sorted(carriles[carril], key=lambda q: q["t"])
            trozos, cursor = [], 0.0
            for a in lista:
                hueco = a["t"] - cursor
                if hueco > 0.002:
                    e = nuevo("g")
                    partes.append(f"anullsrc=r=48000:cl=stereo:d={_f(hueco)},{formato}[{e}]")
                    trozos.append(e)
                k = indice[a["id"]]
                pista = s if P.es_clip(a) else 0
                canales = 2 if a["id"] in audio_wav else _canales_pista(a["archivo"], pista)
                kf = a.get("kf") or {}
                cad = f"[{k}:a:{pista}]aresample=48000,{R._a_estereo(canales)},aformat=sample_fmts=fltp"
                if P.es_clip(a):
                    cad += f",atrim=start={_f(a['desde'])}:duration={_f(P.consumo(a))},asetpts=PTS-STARTPTS"
                cad += R._atempo(a["velocidad"])
                if kf.get("volumen"):
                    cad += f",volume=eval=frame:volume='{P.expr_kf(kf['volumen'])}'"
                else:
                    cad += f",volume={_f(a['volumen'])}"
                if a["fundido_in"] > 0:
                    cad += f",afade=t=in:st=0:d={_f(a['fundido_in'])}"
                if a["fundido_out"] > 0:
                    cad += f",afade=t=out:st={_f(max(0.0, a['dur'] - a['fundido_out']))}:d={_f(a['fundido_out'])}"
                cad += f",apad=whole_dur={_f(a['dur'])},atrim=end={_f(a['dur'])},asetpts=PTS-STARTPTS,{formato}"
                e = nuevo("q")
                partes.append(cad + f"[{e}]")
                trozos.append(e)
                cursor = a["t"] + a["dur"]
            if len(trozos) == 1:
                etiquetas_carril.append(trozos[0])
            else:
                e = nuevo("c")
                partes.append("".join(f"[{x}]" for x in trozos) + f"concat=n={len(trozos)}:v=0:a=1[{e}]")
                etiquetas_carril.append(e)
        salida_audio = f"a{s}out"
        if not etiquetas_carril:
            partes.append(f"anullsrc=r=48000:cl=stereo:d={_f(total)},{formato}[{salida_audio}]")
        elif len(etiquetas_carril) == 1:
            partes.append(f"[{etiquetas_carril[0]}]apad=whole_dur={_f(total)},atrim=end={_f(total)},asetpts=PTS-STARTPTS[{salida_audio}]")
        else:
            base = nuevo("b")
            partes.append(f"anullsrc=r=48000:cl=stereo:d={_f(total)},{formato}[{base}]")
            n = len(etiquetas_carril) + 1
            compensa = "" if norm else f",volume={n}"
            partes.append(f"[{base}]" + "".join(f"[{x}]" for x in etiquetas_carril) +
                          f"amix=inputs={n}:duration=first:dropout_transition=0{norm}{compensa},atrim=end={_f(total)},asetpts=PTS-STARTPTS[{salida_audio}]")
        mapas.append(f"[{salida_audio}]")
    audios = [m for m in mapas[1:]]
    if len(audios) > 1:        # el clip trae varias pistas de audio: se mezclan en UNA (un reproductor solo toca la primera y las demás se perderían)
        n = len(audios)
        compensa = "" if norm else f",volume={n}"
        partes.append("".join(audios) + f"amix=inputs={n}:duration=longest:dropout_transition=0{norm}{compensa},alimiter=limit=0.97,{formato}[aunica]")
        mapas = [mapas[0], "[aunica]"]
    if solo_audio:         # solo el montaje del audio (sin tocar el vídeo): sirve para comprobarlo o rehacerlo aparte
        return {"entradas": [x for e in entradas for x in e], "filtro": ";".join(partes[inicio_audio:]), "mapas": mapas[1:], "total": total,
                "n_entradas": len(entradas)}
    return {"entradas": [x for e in entradas for x in e], "filtro": ";".join(partes), "mapas": mapas, "total": total, "n_entradas": len(entradas)}
