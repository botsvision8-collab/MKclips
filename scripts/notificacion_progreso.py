"""
Ventanita de progreso estilo Skeuomorfismo + icono en la bandeja del sistema.

- La ventana se puede CERRAR (click) sin terminar el proceso: se oculta,
  no se destruye.
- El icono en la bandeja del sistema se queda mientras el pipeline corre.
  Click derecho > "Mostrar progreso" la vuelve a traer, en el mismo lugar.
- Click derecho > "Cerrar" termina todo (ventana + icono).
- Se cierra sola (ventana e icono) un rato despues de terminar (LISTO/ERROR),
  pero NO mientras queden streams pendientes en la cola: en ese caso muestra
  "Stream i/N" y sigue esperando al siguiente.
- Lee estado_progreso.json (escrito por procesar_multiples.py) y muestra
  archivo, paso actual y ETA estimado.

Uso: python notificacion_progreso.py [ruta_al_estado_progreso.json]
Si no se pasa ruta, usa "estado_progreso.json" en la carpeta actual.
"""
import tkinter as tk
import sys
import os
import json
import threading
import traceback

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_DISPONIBLE = True
except ImportError:
    TRAY_DISPONIBLE = False

PERSISTENTE = "--persistente" in sys.argv
argumentos = [a for a in sys.argv[1:] if a != "--persistente"]
ARCHIVO_ESTADO = argumentos[0] if argumentos else "estado_progreso.json"
ARCHIVO_LOCK = os.path.join(os.path.dirname(os.path.abspath(ARCHIVO_ESTADO)) or ".", "notificacion.lock")

ARCHIVO_LOG = os.path.join(os.path.dirname(os.path.abspath(ARCHIVO_ESTADO)) or ".", "notificacion_error.log")


def _registrar_error(texto):
    """Con pythonw no hay consola: sin este log un fallo seria invisible."""
    try:
        with open(ARCHIVO_LOG, "a", encoding="utf-8") as f:
            f.write(texto + "\n")
    except OSError:
        pass


sys.excepthook = lambda tipo, valor, tb: _registrar_error("".join(traceback.format_exception(tipo, valor, tb)))


def _barra_texto(porcentaje, ancho=20):
    """Barra de progreso en texto, ej: '████████░░░░░░░░ 42%'."""
    if porcentaje is None:
        return ""
    porcentaje = max(0, min(100, porcentaje))
    llenos = int(round(ancho * porcentaje / 100))
    return "█" * llenos + "░" * (ancho - llenos) + f" {porcentaje}%"


# El modo persistente comparte el mismo lock que usa el pipeline, evitando
# iconos/ventanas duplicados. Si ya existe, el icono existente permite abrirla.
if PERSISTENTE:
    if os.path.exists(ARCHIVO_LOCK):
        sys.exit(0)
    with open(ARCHIVO_LOCK, "w", encoding="utf-8") as _lock:
        _lock.write("persistente")


def _formatear_eta(segundos):
    if segundos is None:
        return "calculando..."
    m, s = divmod(max(0, int(segundos)), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m restantes"
    return f"{m}m {s:02d}s restantes"


ANCHO, ALTO = 400, 130
RADIO = 14

COLOR_METAL_CLARO = "#8a8f96"
COLOR_METAL_BASE = "#5a5f66"
COLOR_METAL_OSCURO = "#3d4147"
COLOR_BISEL_CLARO = "#c8ccd1"
COLOR_BISEL_OSCURO = "#25272b"
COLOR_PANTALLA = "#0c1a0f"
COLOR_TEXTO_LCD = "#7CFC9A"

root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)

pantalla_ancho = root.winfo_screenwidth()
pantalla_alto = root.winfo_screenheight()
pos_x = pantalla_ancho - ANCHO - 20
pos_y = pantalla_alto - ALTO - 60
root.geometry(f"{ANCHO}x{ALTO}+{pos_x}+{pos_y}")

root.configure(bg="#010101")
try:
    root.wm_attributes("-transparentcolor", "#010101")
except tk.TclError:
    pass

canvas = tk.Canvas(root, width=ANCHO, height=ALTO, bg="#010101", highlightthickness=0)
canvas.pack()


def rect_redondeado(cv, x1, y1, x2, y2, r, **kwargs):
    puntos = [
        x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
        x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
        x1, y2, x1, y2-r, x1, y1+r, x1, y1,
    ]
    return cv.create_polygon(puntos, smooth=True, **kwargs)


rect_redondeado(canvas, 4, 5, ANCHO-2, ALTO-1, RADIO, fill="#000000", outline="")
rect_redondeado(canvas, 0, 0, ANCHO-6, ALTO-6, RADIO, fill=COLOR_METAL_OSCURO, outline="")
rect_redondeado(canvas, 2, 2, ANCHO-8, ALTO-8, RADIO-2, fill=COLOR_METAL_BASE, outline="")
rect_redondeado(canvas, 3, 3, ANCHO-9, ALTO-10, RADIO-3, fill=COLOR_METAL_CLARO, outline="", stipple="gray25")

canvas.create_line(14, 8, ANCHO-20, 8, fill=COLOR_BISEL_CLARO, width=1)
canvas.create_line(14, ALTO-12, ANCHO-20, ALTO-12, fill=COLOR_BISEL_OSCURO, width=1)

led = canvas.create_oval(16, 16, 34, 34, fill="#e0a000", outline="#3d4147", width=2)
led_brillo = canvas.create_oval(19, 18, 25, 23, fill="#ffe08a", outline="")

rect_redondeado(canvas, 44, 14, ANCHO-16, ALTO-14, 6, fill=COLOR_BISEL_OSCURO, outline="")
rect_redondeado(canvas, 46, 16, ANCHO-18, ALTO-16, 5, fill=COLOR_PANTALLA, outline="")

texto_id = canvas.create_text(
    56, ALTO/2, anchor="w", text="Iniciando...",
    fill=COLOR_TEXTO_LCD, font=("Consolas", 9), width=ANCHO-80, justify="left"
)

evento_mostrar = threading.Event()
proceso_terminado = threading.Event()
icono_tray = None


def set_led(color_base, color_brillo):
    canvas.itemconfig(led, fill=color_base)
    canvas.itemconfig(led_brillo, fill=color_brillo)


def ocultar_ventana(event=None):
    root.withdraw()  # se oculta, NO se destruye - se puede recuperar desde el tray


def cerrar_todo():
    proceso_terminado.set()
    if icono_tray:
        icono_tray.stop()
    try:
        if os.path.exists(ARCHIVO_LOCK):
            os.remove(ARCHIVO_LOCK)
    except OSError:
        pass
    root.after(0, root.destroy)


if TRAY_DISPONIBLE:
    canvas.bind("<Button-1>", ocultar_ventana)
else:
    # Sin pystray/Pillow no hay forma de recuperar la ventana si se oculta,
    # asi que mejor no se puede ocultar - solo se cierra sola al terminar.
    pass


def crear_icono_imagen():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(img)
    dibujo.ellipse((4, 4, 60, 60), fill="#5a5f66", outline="#25272b", width=3)
    dibujo.ellipse((20, 20, 44, 44), fill="#e0a000")
    return img


def accion_mostrar(icon, item):
    evento_mostrar.set()


def accion_cerrar(icon, item):
    cerrar_todo()


def iniciar_tray():
    global icono_tray
    menu = pystray.Menu(
        pystray.MenuItem("Mostrar progreso", accion_mostrar, default=True),
        pystray.MenuItem("Cerrar", accion_cerrar),
    )
    icono_tray = pystray.Icon("pipeline_clips", crear_icono_imagen(), "Pipeline de clips", menu)
    icono_tray.run()


if TRAY_DISPONIBLE:
    hilo_tray = threading.Thread(target=iniciar_tray, daemon=True)
    hilo_tray.start()


def revisar_solicitud_mostrar():
    if evento_mostrar.is_set():
        root.deiconify()
        root.lift()
        evento_mostrar.clear()
    if not proceso_terminado.is_set():
        root.after(300, revisar_solicitud_mostrar)


cierre = {"id": None}


def _programar_cierre(ms):
    if cierre["id"] is None:
        cierre["id"] = root.after(ms, cerrar_todo)


def _cancelar_cierre():
    if cierre["id"] is not None:
        root.after_cancel(cierre["id"])
        cierre["id"] = None


def actualizar():
    texto = "Iniciando..."
    terminado = False
    error = False
    quedan = False
    try:
        with open(ARCHIVO_ESTADO, "r", encoding="utf-8") as f:
            estado = json.load(f)
        archivo = estado.get("archivo", "")
        mensaje = estado.get("mensaje", "")
        paso = estado.get("paso_actual")
        total = estado.get("total_pasos")
        error = bool(estado.get("error"))
        terminado = bool(estado.get("terminado"))
        cola_total = int(estado.get("cola_total") or 0)
        cola_indice = int(estado.get("cola_indice") or 0)
        # Quedan streams por procesar mientras la cola siga activa y no sea el ultimo.
        quedan = bool(estado.get("cola_activa")) and cola_indice < cola_total
        prefijo = f"Stream {cola_indice}/{cola_total} - " if cola_total > 1 and cola_indice else ""

        if error:
            texto = f"{prefijo}ERROR: {archivo}\n{mensaje}"
        elif terminado:
            texto = f"{prefijo}LISTO: {archivo}"
        else:
            eta_txt = _formatear_eta(estado.get("eta_segundos"))
            paso_txt = f"Paso {paso}/{total}: " if paso and total else ""
            porcentaje = estado.get("porcentaje")
            barra = f"\n{_barra_texto(porcentaje)}" if porcentaje is not None else ""
            texto = f"{prefijo}{archivo}\n{paso_txt}{mensaje} - {eta_txt}{barra}"
        if (error or terminado) and quedan:
            texto += "\nSiguiente stream en cola..."
    except (OSError, ValueError):
        texto = "Sin procesamiento activo\nSin contexto de stream disponible"

    canvas.itemconfig(texto_id, text=texto)

    if PERSISTENTE:
        set_led("#e0a000", "#ffe08a")
    elif (error or terminado) and not quedan:
        set_led(*(("#c0392b", "#ff8a75") if error else ("#2ecc71", "#b6ffcf")))
        # Con el tray disponible: 1 min para revisar un error, 30 s si todo salio bien.
        _programar_cierre(60000 if error else 30000)
    else:
        # En curso, o terminado pero con mas streams en cola: no se cierra y, si
        # habia un cierre programado, se cancela porque empezo otro stream.
        _cancelar_cierre()
        set_led(*(("#c0392b", "#ff8a75") if error else ("#e0a000", "#ffe08a")))
    if not proceso_terminado.is_set():
        root.after(500, actualizar)


try:
    actualizar()
    revisar_solicitud_mostrar()
    root.mainloop()
except Exception:
    _registrar_error(traceback.format_exc())
finally:
    # Si la ventana termina de cualquier forma, no debe quedar un lock huerfano.
    try:
        if not PERSISTENTE and os.path.exists(ARCHIVO_LOCK):
            os.remove(ARCHIVO_LOCK)
    except OSError:
        pass
