"""Tema y navegación desplazable de la interfaz."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk

PALETAS = {
    "Modo oscuro": dict(fondo="#151922", panel="#202633", texto="#eef2f8", entrada="#111620", borde="#3c485e", activo="#344766", exito="#65d6a0", aviso="#ffd37a", error="#ff9292", info="#91beff"),
    "Modo claro": dict(fondo="#edf1f7", panel="#ffffff", texto="#172338", entrada="#ffffff", borde="#b1bdce", activo="#d5e4fa", exito="#167447", aviso="#885b00", error="#b52535", info="#235ca8"),
}
RUTA_TEMA = Path(__file__).with_name("tema_usuario.json")


def leer_tema():
    try:
        tema = json.loads(RUTA_TEMA.read_text(encoding="utf-8"))["tema"]
        return tema if tema in PALETAS else "Modo oscuro"
    except (OSError, ValueError, KeyError):
        return "Modo oscuro"


def aplicar_tema(root, tema, guardar=False):
    p = PALETAS[tema]
    estilo = ttk.Style(root)
    estilo.theme_use("clam")
    estilo.configure(".", background=p["panel"], foreground=p["texto"], fieldbackground=p["entrada"], bordercolor=p["borde"], troughcolor=p["fondo"], selectbackground=p["activo"], selectforeground=p["texto"])
    for nombre in ("TButton", "TCombobox", "TSpinbox", "TCheckbutton"):
        estilo.map(nombre, background=[("active", p["activo"]), ("selected", p["activo"])], foreground=[("disabled", p["borde"]), ("readonly", p["texto"])], fieldbackground=[("readonly", p["entrada"])])
    for nombre in ("exito", "aviso", "error", "info"):
        estilo.configure(nombre + ".TLabel", foreground=p[nombre])
    # Tablas (cola de streams): sin esto el tema "clam" dibuja filas blancas con
    # texto claro y no se lee nada.
    estilo.configure("Treeview", background=p["entrada"], fieldbackground=p["entrada"], foreground=p["texto"], bordercolor=p["borde"], rowheight=24)
    estilo.map("Treeview", background=[("selected", p["activo"])], foreground=[("selected", p["texto"])])
    estilo.configure("Treeview.Heading", background=p["panel"], foreground=p["texto"], bordercolor=p["borde"], relief="flat")
    estilo.map("Treeview.Heading", background=[("active", p["activo"])])
    root.configure(background=p["fondo"])
    root.option_add("*TCombobox*Listbox.background", p["entrada"])
    root.option_add("*TCombobox*Listbox.foreground", p["texto"])
    def visitar(w):
        if isinstance(w, (tk.Canvas, tk.Text, tk.Listbox)):
            w.configure(background=p["entrada"])
            if isinstance(w, (tk.Text, tk.Listbox)):
                w.configure(foreground=p["texto"], selectbackground=p["activo"])
            if isinstance(w, tk.Text):
                w.configure(insertbackground=p["texto"])
        for hijo in w.winfo_children(): visitar(hijo)
    visitar(root)
    if guardar:
        RUTA_TEMA.write_text(json.dumps({"tema": tema}), encoding="utf-8")


def texto_adaptable(contenedor, etiqueta, margen=0, minimo=180):
    """Hace que ``etiqueta`` ajuste sus saltos de linea al ancho de ``contenedor``.

    Un Label con ``wraplength`` fijo se corta cuando la ventana es mas estrecha que ese
    valor; asi el texto siempre se lee completo, aunque cambie el tamano de la ventana."""
    def ajustar(_evento=None):
        try:
            ancho = contenedor.winfo_width()
            if ancho > 1:
                # ``margen`` puede ser una funcion: asi se descuenta el ancho REAL de lo que
                # comparte la fila (miniatura, estado...) y no un numero fijo.
                descontar = margen() if callable(margen) else margen
                etiqueta.configure(wraplength=max(minimo, ancho - descontar))
        except tk.TclError:
            pass
    contenedor.bind("<Configure>", ajustar, add="+")
    return ajustar


def pagina_scroll(parent):
    exterior = ttk.Frame(parent)
    exterior.columnconfigure(0, weight=1); exterior.rowconfigure(0, weight=1)
    canvas = tk.Canvas(exterior, highlightthickness=0)
    barra = ttk.Scrollbar(exterior, orient="vertical", command=canvas.yview)
    interior = ttk.Frame(canvas, padding=8)
    ventana = canvas.create_window((0, 0), window=interior, anchor="nw")
    canvas.configure(yscrollcommand=barra.set)
    canvas.grid(row=0, column=0, sticky="nsew"); barra.grid(row=0, column=1, sticky="ns")
    interior.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(ventana, width=e.width))
    exterior.canvas_scroll = canvas
    return exterior, interior
