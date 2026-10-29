# -*- coding: utf-8 -*-
"""Rutas del editor nativo (Flask blueprint que se monta en el panel de MKClips).

Solo se puede editar un clip que esté en el catálogo de clips (su id es un hash de la ruta), y
el navegador nunca recibe rutas del disco: pide por id. Las tareas largas (preparar la vista previa,
transcribir, renderizar) corren en hilos y el navegador pregunta su estado cada segundo.
"""
from __future__ import annotations

import hashlib
import re
import gzip
import json
import os
import subprocess
try:
    from .rutas_app import comando_python, datos_dir, recursos_dir
except ImportError:
    from rutas_app import comando_python, datos_dir, recursos_dir
import sys
import threading
import time
import io
from datetime import datetime
import traceback
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, send_file

try:
    from . import catalogo_clips, editor_encuadre, editor_fuentes, editor_ia, editor_modelo as modelo, editor_render as render, editor_subtitulos, editor_seguimiento
    from .configuracion_central import leer_configuracion
except ImportError:  # módulo suelto desde scripts/
    import catalogo_clips
    import editor_encuadre
    import editor_fuentes
    import editor_ia
    import editor_modelo as modelo
    import editor_render as render
    import editor_subtitulos
    import editor_seguimiento
    from configuracion_central import leer_configuracion

if getattr(sys, "frozen", False):
    render.CARPETA_CACHE = str(datos_dir() / ".mkclips_cache" / "editor")
CARPETA_WEB = Path(__file__).resolve().parent / "editor_web"
bp = Blueprint("editor", __name__, url_prefix="/editor")
SELLO = "2026-10-27-b"
VERSION_EDITOR = 14       # sube cuando cambian las rutas: la app avisa si el panel abierto es más antiguo
_TRABAJOS = {}          # (tipo, id_clip) -> estado de la tarea
_CANCELAR = {}          # id_clip -> threading.Event
_CANCELAR_SEGUIMIENTO = {}
_BLOQUEO = threading.Lock()
_MEDIOS = {}            # id de medio -> {"ruta", "info"}; solo estos archivos se sirven al navegador


def _carpeta_resultados():
    return leer_configuracion().get("CARPETA_RESULTADOS") or str(Path(__file__).resolve().parent / "resultados")


def _registrar_exportacion(ruta_clip, salida):
    ruta = os.path.join(_carpeta_resultados(), "exportados.json")
    try:
        with open(ruta, "r", encoding="utf-8") as f: datos = json.load(f)
        if not isinstance(datos, dict): datos = {}
    except (OSError, ValueError): datos = {}
    clave = os.path.normcase(os.path.abspath(ruta_clip))
    datos[clave] = {"ruta_clip": os.path.abspath(ruta_clip), "fecha": datetime.now().astimezone().isoformat(timespec="minutes"), "salida": os.path.abspath(salida)}
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f: json.dump(datos, f, ensure_ascii=False, indent=2)
    os.replace(temporal, ruta)


id_de_clip = modelo.id_de_clip


def buscar_clip(id_clip):
    """Entrada del catálogo con ese id (con su archivo existente) o None."""
    for entrada in catalogo_clips.cargar_catalogo(_carpeta_resultados()):
        ruta = entrada.get("ruta_archivo")
        if ruta and id_de_clip(ruta) == id_clip and os.path.isfile(ruta):
            return entrada
    return None


def _error(mensaje, codigo=400):
    return jsonify(ok=False, error=mensaje), codigo


def _entrada_o_404(id_clip):
    entrada = buscar_clip(id_clip)
    return (entrada, None) if entrada else (None, _error("Ese clip ya no está en el catálogo o su archivo no existe.", 404))


def _estado_trabajo(tipo, id_clip):
    with _BLOQUEO:
        return dict(_TRABAJOS.get((tipo, id_clip)) or {"estado": "sin_iniciar"})


def _poner(tipo, id_clip, **datos):
    with _BLOQUEO:
        _TRABAJOS.setdefault((tipo, id_clip), {}).update(datos)


def _lanzar(tipo, id_clip, objetivo, **inicial):
    """Arranca ``objetivo(actualizar)`` en un hilo. Devuelve False si ya hay una tarea igual en curso."""
    with _BLOQUEO:
        actual = _TRABAJOS.get((tipo, id_clip))
        if actual and actual.get("estado") == "trabajando":
            return False
        _TRABAJOS[(tipo, id_clip)] = {"estado": "trabajando", "mensaje": "", "progreso": 0.0, **inicial}

    def correr():
        try:
            objetivo(lambda **d: _poner(tipo, id_clip, **d))
        except render.Cancelado:
            _poner(tipo, id_clip, estado="cancelado", mensaje="Cancelado.")
        except Exception as exc:  # noqa: BLE001 - el motivo llega al navegador
            traceback.print_exc()
            _poner(tipo, id_clip, estado="error", mensaje=str(exc) or exc.__class__.__name__)
    threading.Thread(target=correr, daemon=True, name=f"editor-{tipo}").start()
    return True


@bp.route("/api/version")
def version():
    try:
        from . import editor_piezas as _pz, editor_render_piezas as _rp
    except ImportError:
        import editor_piezas as _pz
        import editor_render_piezas as _rp
    sellos = {"rutas": SELLO, "piezas": getattr(_pz, "SELLO", "?"), "render": getattr(render, "SELLO", "?"), "render_piezas": getattr(_rp, "SELLO", "?")}
    return jsonify(ok=True, version=VERSION_EDITOR, sellos=sellos)


@bp.route("/api/<id_clip>/diagnosticar", methods=["POST"])
def diagnosticar(id_clip):
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo: return fallo
    def trabajo(actualizar):
        try:
            from . import diagnosticar_edicion as diag
        except ImportError:
            import diagnosticar_edicion as diag
        lineas = []
        ruta_txt = os.path.join(os.path.dirname(entrada["ruta_archivo"]), "diagnostico_edicion.txt")
        def salida(m):
            lineas.append(str(m)); actualizar(mensaje=str(m)[-240:], progreso=min(.95, len(lineas) / 30))
        diag.diagnosticar(entrada["ruta_archivo"], salida=salida)
        actualizar(estado="listo", mensaje="Diagnóstico terminado.", progreso=1, resultado="\n".join(lineas), archivo_txt=ruta_txt)
    if not _lanzar("diagnostico", id_clip, trabajo): return _error("Ya hay un diagnóstico en curso.", 409)
    return jsonify(ok=True)


@bp.route("/api/<id_clip>/diagnosticar/estado")
def diagnosticar_estado(id_clip):
    return jsonify(_estado_trabajo("diagnostico", id_clip))


@bp.route("/api/<id_clip>/diagnosticar/descargar")
def diagnosticar_descargar(id_clip):
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo: return fallo
    ruta = os.path.join(os.path.dirname(entrada["ruta_archivo"]), "diagnostico_edicion.txt")
    if not os.path.isfile(ruta): return _error("Todavía no hay un diagnóstico para descargar.", 404)
    return send_file(ruta, as_attachment=True, download_name="diagnostico_edicion.txt")


@bp.route("/api/<id_clip>/reiniciar", methods=["POST"])
def reiniciar(id_clip):
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo: return fallo
    if request.remote_addr not in ("127.0.0.1", "::1"): return _error("Solo se permite desde el equipo local.", 403)
    # Reinicio diferido: el hilo espera a liberar el puerto y vuelve a iniciar el panel.
    if getattr(sys, "frozen", False):
        comando_panel = [sys.executable, "--server"]
        carpeta_panel = Path(sys.executable).resolve().parent
    else:
        script = str(Path(__file__).resolve().with_name("panel_grabacion.py"))
        comando_panel = [sys.executable, script]
        carpeta_panel = Path(script).parent
    def reiniciar_panel():
        limite = time.time() + 30
        while time.time() < limite:
            try:
                socket.create_connection(("127.0.0.1", 5678), timeout=.3).close()
                time.sleep(.25)
            except OSError:
                break
        try:
            subprocess.Popen(comando_panel, cwd=str(carpeta_panel), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
        except OSError:
            pass
    if getattr(sys, "frozen", False):
        threading.Thread(target=reiniciar_panel, daemon=True).start()
    else:
        espera = "import socket,time,subprocess,sys; s=('127.0.0.1',5678); d=time.time()+30\nwhile time.time()<d:\n try:\n  x=socket.create_connection(s,.3); x.close(); time.sleep(.25)\n except OSError: break\nsubprocess.Popen(" + repr(comando_panel) + ",cwd=" + repr(str(carpeta_panel)) + ",stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)"
        subprocess.Popen([sys.executable, "-c", espera], cwd=str(carpeta_panel), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True,
                         start_new_session=(os.name != "nt"))
    threading.Timer(.5, lambda: os._exit(0)).start()
    return jsonify(ok=True, version_nueva=VERSION_EDITOR)


# ----------------------------------------------------------------------------- página
@bp.route("/<id_clip>")
def pagina(id_clip):
    if not buscar_clip(id_clip):
        return Response("Ese clip ya no está en el catálogo.", status=404, mimetype="text/plain; charset=utf-8")
    html = (CARPETA_WEB / "editor.html").read_text(encoding="utf-8")
    html = re.sub(r"(/editor/static/[A-Za-z0-9_.]+)\?v=[0-9A-Za-z]+", lambda m: f"{m.group(1)}?v={_version_estaticos()}", html)      # la caché del navegador se renueva sola si cambia un archivo
    respuesta = Response(html, mimetype="text/html")
    respuesta.headers["Cache-Control"] = "no-store"
    tema = "oscuro"
    try:
        datos_tema = json.loads((Path(__file__).resolve().parent / "tema_usuario.json").read_text(encoding="utf-8"))
        if "claro" in str(datos_tema.get("tema", "")).lower(): tema = "claro"
    except (OSError, ValueError, AttributeError): pass
    respuesta.set_cookie("mkclips_theme", tema, samesite="Lax")
    return respuesta


def _version_estaticos():
    h = hashlib.sha256()
    for nombre in sorted(_ARCHIVOS_WEB):
        try:
            h.update((CARPETA_WEB / nombre).read_bytes())
        except OSError:
            pass
    return h.hexdigest()[:10]


_ARCHIVOS_WEB = {
    "editor_piezas.js": "application/javascript",
    "editor_app.js": "application/javascript",
    "editor.css": "text/css",
}


def _gzip_si_corresponde(respuesta):
    if (respuesta.status_code != 200 or respuesta.headers.get("Content-Encoding")
            or not request.accept_encodings.quality("gzip") > 0
            or respuesta.mimetype not in ("text/html", "text/css", "application/javascript", "application/json")):
        return respuesta
    datos = respuesta.get_data()
    if len(datos) < 700:
        return respuesta
    respuesta.set_data(gzip.compress(datos, compresslevel=6, mtime=0))
    respuesta.headers["Content-Encoding"] = "gzip"
    respuesta.vary.add("Accept-Encoding")
    return respuesta


@bp.after_app_request
def comprimir_respuestas_editor(respuesta):
    if request.path.startswith("/editor/"):
        return _gzip_si_corresponde(respuesta)
    return respuesta


@bp.route("/static/<nombre>")
def archivo_web(nombre):
    """Recursos estáticos versionados, con ETag y caché del navegador."""
    tipo = _ARCHIVOS_WEB.get(nombre)
    ruta = CARPETA_WEB / nombre
    if not tipo or not ruta.is_file():
        return Response("No existe.", status=404, mimetype="text/plain; charset=utf-8")
    datos = ruta.read_bytes()
    respuesta = Response(datos, mimetype=tipo)
    respuesta.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    respuesta.set_etag(hashlib.sha256(datos).hexdigest())
    return respuesta.make_conditional(request)


# ----------------------------------------------------------------------------- estado y vista previa
def _edicion_de(entrada):
    ruta = entrada["ruta_archivo"]
    info = render.sondear(ruta)
    base = modelo.edicion_nueva(ruta, info["duracion"], info["ancho"], info["alto"], info["pistas_audio"], info["fps"],
                                editor_fuentes.fuente_por_defecto())
    guardada = modelo.cargar_edicion(ruta)
    return (modelo.normalizar_edicion(guardada, base) if guardada else base), info, bool(guardada)


def _preparar_vista(id_clip, ruta, info):
    def trabajo(actualizar):
        actualizar(mensaje="Preparando la vista previa…")
        render.crear_proxy(ruta, info)
        actualizar(estado="listo", mensaje="", progreso=1.0)
    if render.video_directo(ruta, info):
        _poner("vista", id_clip, estado="listo", mensaje="", progreso=1.0, directo=True)
    elif os.path.isfile(render.ruta_proxy(ruta)):
        _poner("vista", id_clip, estado="listo", mensaje="", progreso=1.0)
    else:
        _lanzar("vista", id_clip, trabajo)


@bp.route("/api/<id_clip>/estado")
def estado(id_clip):
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo:
        return fallo
    try:
        edicion, info, guardada = _edicion_de(entrada)
    except ValueError as exc:
        return _error(str(exc))
    if _estado_trabajo("vista", id_clip)["estado"] in ("sin_iniciar", "error"):
        _preparar_vista(id_clip, entrada["ruta_archivo"], info)
    medios_usados = [p for p in edicion.get("piezas", []) if p.get("fuente") == "medio"]
    for extra in medios_usados:
        extra["mid"] = id_de_medio(extra["archivo"])
        try:
            _registrar_medio(id_clip, extra["archivo"], preparar=True)
        except (ValueError, OSError):
            pass
    clip = entrada.get("clip") or {}
    ok_cara, mensaje_cara = editor_encuadre.detector_disponible()
    return jsonify(ok=True, version=VERSION_EDITOR, titulo=(clip.get("titulo") or "").strip() or os.path.basename(entrada["ruta_archivo"]),
                   edicion=edicion, edicion_guardada=guardada, info=info,
                   medios={extra["mid"]: _datos_medio(extra["archivo"]) for extra in medios_usados},
                   vista=_estado_trabajo("vista", id_clip), fuentes=[f["familia"] for f in editor_fuentes.listar_fuentes()],
                   cara={"disponible": ok_cara, "mensaje": mensaje_cara},
                   ia=_estado_ia(),
                   subtitulos_stream=bool(clip.get("segmentos")) and _transcripcion_del_clip(entrada) is not None,
                   salida=render.nombre_salida(entrada["ruta_archivo"]))


@bp.route("/api/<id_clip>/vista")
def vista_estado(id_clip):
    return jsonify(_estado_trabajo("vista", id_clip))


@bp.route("/api/<id_clip>/video")
def video(id_clip):
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo:
        return fallo
    try:
        info = render.sondear(entrada["ruta_archivo"])
    except ValueError as exc:
        return _error(str(exc), 400)
    if render.video_directo(entrada["ruta_archivo"], info):
        return send_file(entrada["ruta_archivo"], mimetype=render.tipo_video_directo(entrada["ruta_archivo"]), conditional=True, max_age=0)
    proxy = render.ruta_proxy(entrada["ruta_archivo"])
    if not os.path.isfile(proxy):
        return _error("La vista previa todavía no está lista.", 409)
    return send_file(proxy, mimetype=render.tipo_proxy(), conditional=True, max_age=0)


@bp.route("/api/<id_clip>/onda")
def onda(id_clip):
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo:
        return fallo
    try:
        info = render.sondear(entrada["ruta_archivo"])
        return jsonify(ok=True, picos=render.onda_de_audio(entrada["ruta_archivo"], info["duracion"]), por_segundo=20)
    except Exception as exc:  # noqa: BLE001
        return jsonify(ok=True, picos=[], por_segundo=20, aviso=str(exc))


# ----------------------------------------------------------------------------- medios extra (B-roll, imágenes, audio)
def id_de_medio(ruta):
    return hashlib.sha1(os.path.normcase(os.path.abspath(ruta)).encode("utf-8")).hexdigest()[:16]


def _datos_medio(ruta):
    mid = id_de_medio(ruta)
    return {"mid": mid, "existe": os.path.isfile(ruta)}


def _registrar_medio(id_clip, ruta, preparar=False):
    """Sondea el medio, lo da de alta y (si ``preparar``) lanza la copia ligera para el navegador."""
    if not ruta or not os.path.isfile(ruta):
        return None
    mid = id_de_medio(ruta)
    with _BLOQUEO:
        registrado = _MEDIOS.get(mid)
    if not registrado:
        info = render.sondear_medio(ruta)
        registrado = {"ruta": os.path.abspath(ruta), "info": info}
        with _BLOQUEO:
            _MEDIOS[mid] = registrado
    if preparar and registrado["info"]["tipo"] == "video" and render.video_directo(registrado["ruta"], registrado["info"]):
        _poner(f"medio-{mid}", id_clip, estado="listo", progreso=1.0, mensaje="", mimetype=render.tipo_video_directo(registrado["ruta"]))
    elif preparar and _estado_trabajo(f"medio-{mid}", id_clip)["estado"] in ("sin_iniciar", "error"):
        def trabajo(actualizar):
            ruta_proxy, tipo = render.crear_proxy_medio(registrado["ruta"], registrado["info"])
            actualizar(estado="listo", progreso=1.0, mensaje="", mimetype=tipo)
        _lanzar(f"medio-{mid}", id_clip, trabajo, mensaje="Preparando…")
    return mid, registrado


def _ficha_medio(mid, registrado):
    info = registrado["info"]
    return {"mid": mid, "archivo": registrado["ruta"], "nombre": os.path.basename(registrado["ruta"]), "tipo": info["tipo"],
            "dur_medio": round(info["duracion"], 3), "ancho": info["ancho"], "alto": info["alto"], "tiene_audio": info["tiene_audio"]}


def _alta_de_medios(id_clip, rutas):
    fichas, errores = [], []
    for ruta in [str(r).strip().strip('"') for r in rutas[:20] if r]:
        nombre = os.path.basename(ruta) or ruta
        if os.path.splitext(ruta)[1].lower() not in render.EXT_MEDIOS:
            errores.append(f"{nombre}: formato no admitido.")
            continue
        try:
            resultado = _registrar_medio(id_clip, ruta, preparar=True)
        except ValueError as exc:
            errores.append(f"{nombre}: {exc}")
            continue
        if resultado:
            fichas.append(_ficha_medio(*resultado))
        else:
            errores.append(f"{nombre}: no existe.")
    return jsonify(ok=bool(fichas), medios=fichas, errores=errores, error="; ".join(errores) if errores and not fichas else "")


@bp.route("/api/<id_clip>/medios/agregar", methods=["POST"])
def medios_agregar(id_clip):
    """Da de alta archivos por ruta (elegidos con el selector del sistema o pegados a mano)."""
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo:
        return fallo
    return _alta_de_medios(id_clip, (request.get_json(silent=True) or {}).get("rutas") or [])


@bp.route("/api/<id_clip>/etiqueta", methods=["POST"])
def crear_etiqueta(id_clip):
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo: return fallo
    datos = request.get_json(silent=True) or {}
    plataforma = str(datos.get("plataforma", "youtube")).lower()
    if plataforma not in ("facebook", "instagram", "twitch", "youtube", "kick", "tiktok", "trovo"):
        return _error("Plataforma no válida.")
    try:
        from PIL import Image, ImageDraw, ImageFont
        refdir = Path(__file__).resolve().parents[1] / "assets" / "etiquetas_referencia"
        refnombre = {"tiktok": "tiktok_live", "trovo": "trovo"}.get(plataforma, plataforma)
        ref = refdir / (refnombre + ("_oscuro" if datos.get("variante") == "oscuro" and (refdir / (refnombre + "_oscuro.png")).exists() else "") + ".png")
        original = Image.open(ref).convert("RGBA")
        # Colores medidos de la zona interior de la píldora y del texto de la referencia.
        fondo_rgb = original.getpixel((110, 60))[:3]
        color_rgb = original.getpixel((180, 60))[:3]
        fuente_icono = Path(__file__).resolve().parents[1] / "assets" / "etiquetas" / (refnombre.replace("_live", "") + ".png")
        icon = Image.open(fuente_icono).convert("RGBA")
        h = 128
        icon = icon.resize((round(icon.width * h / icon.height), h), Image.Resampling.LANCZOS)
        if plataforma == "trovo" and datos.get("variante") == "oscuro" and not (refdir / "trovo_oscuro.png").exists():
            fondo_rgb, color_rgb = (22, 29, 25), (245, 255, 248)
        fondo = (*fondo_rgb, 255)
        color = (*color_rgb, 255)
        tam = max(16, min(160, int(datos.get("tamano", 46))))
        fuente_nombre = str(datos.get("fuente", "Arial"))
        try:
            from . import editor_fuentes
        except ImportError: import editor_fuentes
        ficha_fuente = editor_fuentes.buscar_familia(fuente_nombre)
        candidatos = (ficha_fuente or {}).get("archivos", [])
        try:
            font = ImageFont.truetype(candidatos[0], tam) if candidatos else ImageFont.truetype("arial.ttf", tam)
        except OSError:
            font = ImageFont.load_default()
        nombre = str(datos.get("nombre", "tu_nombre"))[:60]
        dummy = ImageDraw.Draw(Image.new("RGBA", (2,2))); bb = dummy.textbbox((0,0), nombre, font=font)
        alto = max(58, tam + 32); iw = round(alto * .78); gap = round(alto * .10); pad = round(alto * .20)
        ancho = pad * 2 + iw + gap + bb[2] - bb[0]
        im = Image.new("RGBA", (ancho, alto), (0,0,0,0)); d = ImageDraw.Draw(im)
        forma = "rectangular" if datos.get("forma") == "rectangular" else "ovalada"
        d.rounded_rectangle((0,0,ancho-1,alto-1), radius=(max(6, round(alto * .16)) if forma == "rectangular" else alto//2), fill=fondo)
        im.alpha_composite(icon.resize((iw,iw), Image.Resampling.LANCZOS), (pad,(alto-iw)//2))
        d.text((pad+iw+gap,(alto-(bb[3]-bb[1]))//2-bb[1]), nombre, font=font, fill=color)
        base = datos_dir() / ".mkclips_cache" / "etiquetas"; base.mkdir(parents=True, exist_ok=True)
        firma = hashlib.sha1((plataforma+str(datos.get("variante"))+forma+nombre+fuente_nombre+str(tam)).encode("utf-8")).hexdigest()
        ruta = str(base / (firma + ".png")); im.save(ruta)
        resultado = _registrar_medio(id_clip, ruta, preparar=True)
        return jsonify(ok=True, medio=_ficha_medio(*resultado))
    except Exception as exc: return _error(f"No se pudo crear la etiqueta: {exc}")


_SCRIPT_SELECTOR = (
    "import json,sys\n"
    "import tkinter as tk\n"
    "from tkinter import filedialog\n"
    "r=tk.Tk(); r.withdraw(); r.attributes('-topmost',True)\n"
    "t=filedialog.askopenfilenames(title='Elige videos, imágenes o audios', filetypes=["
    "('Videos, imágenes y audios','*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.png *.jpg *.jpeg *.webp *.gif *.mp3 *.wav *.m4a *.aac *.ogg *.opus *.flac'),('Todos','*.*')])\n"
    "print(json.dumps(list(t)))\n")


@bp.route("/api/<id_clip>/medios/elegir", methods=["POST"])
def medios_elegir(id_clip):
    """Abre el selector de archivos del sistema (el servidor corre en el mismo ordenador que el navegador)."""
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo:
        return fallo
    try:
        cmd_selector = comando_python("seleccionar_medios.py") if getattr(sys, "frozen", False) else [sys.executable, "-c", _SCRIPT_SELECTOR]
        r = subprocess.run(cmd_selector, capture_output=True, text=True, timeout=900,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
        rutas = json.loads((r.stdout or "").strip().splitlines()[-1]) if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        rutas = None
    if rutas is None:
        return jsonify(ok=False, sin_selector=True, error="No se pudo abrir el selector de archivos. Pega la ruta del archivo."), 200
    if not rutas:
        return jsonify(ok=True, medios=[], cancelado=True)
    return _alta_de_medios(id_clip, rutas)


def _medio_o_404(mid):
    with _BLOQUEO:
        registrado = _MEDIOS.get(mid)
    if not registrado or not os.path.isfile(registrado["ruta"]):
        return None, _error("Medio desconocido.", 404)
    return registrado, None


@bp.route("/api/<id_clip>/medio/<mid>/estado")
def medio_estado(id_clip, mid):
    registrado, fallo = _medio_o_404(mid)
    if fallo:
        return fallo
    return jsonify(_estado_trabajo(f"medio-{mid}", id_clip))


@bp.route("/api/<id_clip>/medio/<mid>")
def medio_archivo(id_clip, mid):
    registrado, fallo = _medio_o_404(mid)
    if fallo:
        return fallo
    if registrado["info"]["tipo"] == "video" and render.video_directo(registrado["ruta"], registrado["info"]):
        return send_file(registrado["ruta"], mimetype=render.tipo_video_directo(registrado["ruta"]), conditional=True, max_age=0)
    try:
        ruta, tipo = render.crear_proxy_medio(registrado["ruta"], registrado["info"]) if _estado_trabajo(f"medio-{mid}", id_clip)["estado"] == "listo" else (None, None)
    except RuntimeError as exc:
        return _error(str(exc), 500)
    if not ruta:
        return _error("El medio todavía no está listo.", 409)
    return send_file(ruta, mimetype=tipo, conditional=True, max_age=0)


@bp.route("/api/<id_clip>/medio/<mid>/onda")
def medio_onda(id_clip, mid):
    registrado, fallo = _medio_o_404(mid)
    if fallo:
        return fallo
    if not registrado["info"]["tiene_audio"]:
        return jsonify(ok=True, picos=[], por_segundo=20)
    try:
        return jsonify(ok=True, picos=render.onda_de_audio(registrado["ruta"], registrado["info"]["duracion"]), por_segundo=20)
    except Exception as exc:  # noqa: BLE001
        return jsonify(ok=True, picos=[], por_segundo=20, aviso=str(exc))


# ----------------------------------------------------------------------------- guardar
@bp.route("/api/<id_clip>/guardar", methods=["POST"])
def guardar(id_clip):
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo:
        return fallo
    edicion, _info, _g = _edicion_de(entrada)
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return _error("Datos de edición inválidos.")
    nueva = modelo.normalizar_edicion(datos, edicion)
    modelo.guardar_edicion(entrada["ruta_archivo"], nueva)
    return jsonify(ok=True, edicion=nueva)


# ----------------------------------------------------------------------------- subtítulos
def _transcripcion_del_clip(entrada):
    """Transcripción del stream de este clip si es la del último stream procesado; si no, None."""
    try:
        base = Path(__file__).resolve().parent
        video_ultimo = (base / "ultimo_video.txt").read_text(encoding="utf-8").splitlines()[0].strip()
        try:
            from .cache_mkclips import identidad_fuente
        except ImportError:
            from cache_mkclips import identidad_fuente
        huella = (entrada.get("fuente") or {}).get("fingerprint")
        if not huella or identidad_fuente(video_ultimo).get("fingerprint") != huella:
            return None
        datos = json.loads((base / "transcripcion.json").read_text(encoding="utf-8"))
        return datos if isinstance(datos, list) else None
    except Exception:  # noqa: BLE001 - es un respaldo opcional
        return None


@bp.route("/api/<id_clip>/subtitulos", methods=["POST"])
def subtitulos(id_clip):
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo:
        return fallo
    origen = (request.get_json(silent=True) or {}).get("origen", "whisper")
    ruta = entrada["ruta_archivo"]
    if origen == "stream":
        segmentos = (entrada.get("clip") or {}).get("segmentos") or []
        transcripcion = _transcripcion_del_clip(entrada)
        if not segmentos or transcripcion is None:
            return _error("La transcripción del stream no está disponible para este clip; usa la transcripción del clip.")

        def trabajo(actualizar):
            lineas = editor_subtitulos.desde_transcripcion(segmentos, transcripcion)
            if not lineas:
                raise RuntimeError("La transcripción del stream no tiene texto en este clip.")
            actualizar(estado="listo", lineas=lineas, mensaje="")
    else:
        def trabajo(actualizar):
            lineas = editor_subtitulos.desde_whisper(ruta, notificar=lambda m: actualizar(mensaje=m))
            actualizar(estado="listo", lineas=lineas, mensaje="")
    if not _lanzar("subtitulos", id_clip, trabajo, mensaje="Preparando…"):
        return _error("Ya se están generando los subtítulos.", 409)
    return jsonify(ok=True)


@bp.route("/api/<id_clip>/subtitulos/estado")
def subtitulos_estado(id_clip):
    return jsonify(_estado_trabajo("subtitulos", id_clip))


# ----------------------------------------------------------------------------- encuadre automático
@bp.route("/api/<id_clip>/seguimiento/analizar", methods=["POST"])
def seguimiento_analizar(id_clip):
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo: return fallo
    if _estado_trabajo("seguimiento", id_clip).get("estado") == "trabajando":
        return _error("Ya hay un análisis en curso.",409)
    ok, mensaje = editor_seguimiento.disponible()
    if not ok: return _error(mensaje, 400)
    info = render.sondear(entrada["ruta_archivo"])
    datos=request.get_json(silent=True) or {}
    region=datos.get("region") if isinstance(datos.get("region"),dict) else {"x":0,"y":0,"w":1,"h":1}
    cancel = threading.Event(); _CANCELAR_SEGUIMIENTO[id_clip] = cancel
    def trabajo(actualizar):
        try:
            suavidad=modelo._num(datos.get("suavidad"),.70,.05,.95)
            perdida="centro" if datos.get("perdida")=="centro" else "mantener"
            trayectoria = editor_seguimiento.analizar(entrada["ruta_archivo"], info["duracion"], suavidad=suavidad, perdida=perdida, region=region, cancelar=cancel,
                progreso=lambda f: actualizar(progreso=round(f,3), mensaje=f"Analizando caras… {round(f*100)}%"))
        except RuntimeError:
            if cancel.is_set(): raise render.Cancelado()
            raise
        if cancel.is_set(): raise render.Cancelado()
        _poner("seguimiento", id_clip, estado="listo", progreso=1, mensaje="Análisis terminado.", trayectoria=trayectoria)
    if not _lanzar("seguimiento", id_clip, trabajo): return _error("Ya hay un análisis en curso.",409)
    return jsonify(ok=True)

@bp.route("/api/<id_clip>/seguimiento/estado")
def seguimiento_estado(id_clip):
    return jsonify(_estado_trabajo("seguimiento", id_clip))

@bp.route("/api/<id_clip>/seguimiento/cancelar", methods=["POST"])
def seguimiento_cancelar(id_clip):
    evento=_CANCELAR_SEGUIMIENTO.get(id_clip)
    if evento: evento.set()
    return jsonify(ok=True)

@bp.route("/api/<id_clip>/cara", methods=["POST"])
def cara(id_clip):
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo:
        return fallo
    ok, mensaje = editor_encuadre.detector_disponible()
    if not ok:
        return jsonify(ok=False, error=mensaje, sin_detector=True), 400
    try:
        info = render.sondear(entrada["ruta_archivo"])
        encontrada = editor_encuadre.detectar_cara(entrada["ruta_archivo"], info["duracion"])
    except Exception as exc:  # noqa: BLE001
        return _error(str(exc))
    if not encontrada:
        return jsonify(ok=True, encontrada=False, mensaje="No encontré ninguna cara de forma fiable. Coloca los recuadros a mano.")
    datos = request.get_json(silent=True) or {}
    prop = float(datos.get("proporcion_arriba") or 0.6)
    salida = datos.get("salida") or {"ancho": 1080, "alto": 1920}
    propuesta = editor_encuadre.proponer_dividido(encontrada, info["ancho"], info["alto"], int(salida.get("ancho", 1080)),
                                                  int(salida.get("alto", 1920)), min(0.8, max(0.2, prop)))
    return jsonify(ok=True, encontrada=True, cara=encontrada, **propuesta)


@bp.route("/api/apagar", methods=["POST"])
def apagar():
    """Cierra este panel (lo usa la app al actualizar para sustituir un panel antiguo). Solo local y con cabecera propia."""
    if request.remote_addr not in ("127.0.0.1", "::1") or request.headers.get("X-MKClips-Apagar") != "1":
        return _error("No permitido.", 403)
    threading.Timer(0.6, lambda: os._exit(0)).start()
    return jsonify(ok=True)


def _destino_de(entrada, edicion, numerar=True):
    carpeta = str(leer_configuracion().get("CARPETA_EDITADOS") or "").strip()
    return render.nombre_salida(entrada["ruta_archivo"], edicion, carpeta, entrada.get("stream") or "", numerar), carpeta


@bp.route("/api/<id_clip>/destino", methods=["POST"])
def destino(id_clip):
    """Dónde se guardará el clip editado con los ajustes actuales (nombre, carpeta general, stream)."""
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo:
        return fallo
    base, _info, _g = _edicion_de(entrada)
    datos = request.get_json(silent=True)
    edicion = modelo.normalizar_edicion(datos, base) if isinstance(datos, dict) else base
    ruta, carpeta = _destino_de(entrada, edicion)
    plano, _c = _destino_de(entrada, edicion, numerar=False)
    return jsonify(ok=True, archivo=ruta, carpeta_base=carpeta, stream=entrada.get("stream") or "", existe=os.path.exists(plano),
                   nombre_defecto=os.path.splitext(os.path.basename(entrada["ruta_archivo"]))[0] + "_editado")


def _estado_ia():
    ok, texto = editor_ia.disponible()
    return {"disponible": ok, "mensaje": "" if ok else texto}


# ----------------------------------------------------------------------------- render
@bp.route("/api/<id_clip>/renderizar", methods=["POST"])
def renderizar(id_clip):
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo:
        return fallo
    ruta = entrada["ruta_archivo"]
    with _BLOQUEO:
        if any(t == "render" and e.get("estado") == "trabajando" for (t, _i), e in _TRABAJOS.items()):
            return _error("Ya hay un render en curso; espera a que termine.", 409)
    edicion, _info, _g = _edicion_de(entrada)
    datos = request.get_json(silent=True)
    if isinstance(datos, dict):
        edicion = modelo.normalizar_edicion(datos, edicion)
        modelo.guardar_edicion(ruta, edicion)
    cancelar = threading.Event()
    _CANCELAR[id_clip] = cancelar
    destino_final, _carpeta = _destino_de(entrada, edicion)

    def trabajo(actualizar):
        actualizar(mensaje="Renderizando…")
        resultado = render.renderizar(edicion, ruta, destino=destino_final, progreso=lambda f: actualizar(progreso=round(f, 3)), cancelar=cancelar, mensaje=lambda m: actualizar(mensaje=m))
        actualizar(estado="listo", progreso=1.0, mensaje="", archivo=resultado["archivo"], codificador=resultado["codificador"],
                   duracion=resultado["duracion"])
        _registrar_exportacion(ruta, resultado["archivo"])
    if not _lanzar("render", id_clip, trabajo):
        return _error("Ya hay un render de este clip en curso.", 409)
    return jsonify(ok=True)


@bp.route("/api/<id_clip>/render/estado")
def render_estado(id_clip):
    return jsonify(_estado_trabajo("render", id_clip))


@bp.route("/api/<id_clip>/render/cancelar", methods=["POST"])
def render_cancelar(id_clip):
    evento = _CANCELAR.get(id_clip)
    if evento:
        evento.set()
    return jsonify(ok=True)


@bp.route("/api/<id_clip>/abrir", methods=["POST"])
def abrir(id_clip):
    """Abre el clip editado (o su carpeta) con el programa del sistema."""
    entrada, fallo = _entrada_o_404(id_clip)
    if fallo:
        return fallo
    try:
        from . import reproductor_sistema
    except ImportError:
        import reproductor_sistema
    ultimo = _estado_trabajo("render", id_clip).get("archivo")
    if ultimo and os.path.isfile(ultimo):
        destino = ultimo                                     # el archivo que se acaba de generar (puede llevar número)
    else:
        edicion, _i, _g = _edicion_de(entrada)
        destino, _c = _destino_de(entrada, edicion, numerar=False)
    if (request.get_json(silent=True) or {}).get("carpeta"):
        destino = os.path.dirname(destino)
        if not os.path.isdir(destino):
            return _error("Todavía no hay clips editados.")
        try:
            if os.name == "nt":
                os.startfile(destino)  # noqa: S606
            else:
                import subprocess
                subprocess.Popen(["xdg-open", destino])
            return jsonify(ok=True)
        except OSError as exc:
            return _error(str(exc))
    ok, mensaje = reproductor_sistema.abrir_en_reproductor(destino)
    return jsonify(ok=True) if ok else _error(mensaje)


def registrar(app):
    """Monta el editor en la app Flask del panel. Nunca rompe el panel si algo falla."""
    try:
        app.register_blueprint(bp)
        return True
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return False

