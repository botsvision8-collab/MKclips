"""
descargar_video.py - Descarga un video/VOD desde un link (YouTube, Twitch,
Kick, TikTok, etc.) usando yt-dlp, para despues correrle el pipeline de
clips igual que a un stream grabado localmente.

Requiere: pip install -U yt-dlp
(Kick y TikTok cambian su web seguido y rompen la extraccion de tanto en
tanto - si falla, lo primero a intentar siempre es actualizar yt-dlp).
"""

import os


def descargar_video(url, carpeta_destino, on_progreso=None):
    """
    Descarga 'url' a 'carpeta_destino' con el mejor video+audio combinado
    (se guarda como .mp4). Devuelve la ruta completa del archivo descargado.

    on_progreso(texto) se llama con actualizaciones legibles para mostrar
    en una UI, si se pasa.

    Lanza RuntimeError con un mensaje claro (incluyendo consejos segun la
    plataforma) si la descarga falla.
    """
    try:
        import yt_dlp
    except ImportError as e:
        raise RuntimeError(
            "Falta la libreria yt-dlp. Instala con: pip install -U yt-dlp"
        ) from e

    os.makedirs(carpeta_destino, exist_ok=True)

    def _hook(d):
        if not on_progreso:
            return
        if d.get("status") == "downloading":
            porcentaje = (d.get("_percent_str") or "").strip()
            velocidad = (d.get("_speed_str") or "").strip()
            on_progreso(f"Descargando... {porcentaje} ({velocidad})".strip())
        elif d.get("status") == "finished":
            on_progreso("Descarga terminada, procesando archivo...")

    opciones = {
        "outtmpl": os.path.join(
            carpeta_destino, "%(extractor)s_%(id)s_%(title).60s.%(ext)s"
        ),
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "restrictfilenames": True,
        "noplaylist": True,
        "progress_hooks": [_hook],
    }

    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget
        opciones["impersonate"] = ImpersonateTarget.from_str("chrome")
    except Exception:
        # curl_cffi no instalado o version de yt-dlp sin soporte de
        # impersonate - seguimos sin eso, Kick puede fallar mas seguido.
        pass

    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(url, download=True)
            ruta = ydl.prepare_filename(info)

            base, _ = os.path.splitext(ruta)
            candidato_mp4 = base + ".mp4"
            if os.path.exists(candidato_mp4):
                ruta = candidato_mp4
    except Exception as e:
        mensaje = str(e) or repr(e)
        url_baja = url.lower()
        if "kick.com" in url_baja:
            pista = (
                "\nKick suele fallar por proteccion anti-bot. Proba:\n"
                "  1) Actualizar yt-dlp: pip install -U yt-dlp\n"
                "  2) pip install curl_cffi (ya deberia estar activo via 'impersonate')."
            )
        elif "tiktok.com" in url_baja:
            pista = "\nTikTok cambia su web seguido. Proba actualizar yt-dlp: pip install -U yt-dlp"
        else:
            pista = ""
        raise RuntimeError(f"No se pudo descargar el video: {mensaje}{pista}") from e

    if not os.path.exists(ruta):
        raise RuntimeError(
            f"La descarga parecio terminar pero no se encontro el archivo: {ruta}"
        )

    return ruta


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python descargar_video.py <url> [carpeta_destino]")
        sys.exit(1)

    url_cli = sys.argv[1]
    try:
        from config import CARPETA_STREAMS as CARPETA_DESTINO_DEFECTO
    except ImportError:
        if getattr(sys, "frozen", False):
            try:
                from rutas_app import datos_dir
            except ImportError:
                from .rutas_app import datos_dir
            CARPETA_DESTINO_DEFECTO = os.path.join(str(datos_dir()), "streams")
        else:
            CARPETA_DESTINO_DEFECTO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "streams")

    destino = sys.argv[2] if len(sys.argv) > 2 else CARPETA_DESTINO_DEFECTO
    ruta_final = descargar_video(url_cli, destino, on_progreso=print)
    print(f"Listo: {ruta_final}")
