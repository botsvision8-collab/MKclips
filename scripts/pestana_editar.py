# -*- coding: utf-8 -*-
"""Pestaña «Editar»: lista de clips ya valorados (con estrellas) y botón para abrir el editor nativo.

Solo muestra miniatura, nombre, estrellas y el botón «Editar»; la edición ocurre en el editor
(una página del panel local que se abre en el navegador). Los hilos nunca tocan Tk: dejan los
resultados en colas y la interfaz las lee con ``after``.
"""
from __future__ import annotations

import os
import json
from datetime import datetime
import queue
import threading
from concurrent.futures import ThreadPoolExecutor

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:  # entornos sin Tk (pruebas): las funciones puras siguen disponibles
    tk = ttk = None

try:
    from . import editor_lanzador
except ImportError:
    import editor_lanzador

REDUCCION_MINIATURA = 3          # las miniaturas de Validar clips miden 320 px; aquí se ven a 1/3
FILTROS = {"Todos los valorados": 1, "3 estrellas o más": 3, "4 estrellas o más": 4, "Solo 5 estrellas": 5}


def estrellas_de(entrada):
    """1..5 si el clip tiene valoración positiva (no descartado), si no 0."""
    if not entrada or entrada.get("discarded"):
        return 0
    rating = entrada.get("rating")
    return rating if isinstance(rating, int) and 1 <= rating <= 5 else 0


def texto_estrellas(n):
    return "★" * n + "☆" * (5 - n)


def titulo_de(clip):
    return (clip.get("titulo") or "").strip() or str(clip.get("razon") or "").strip()[:90] or "Clip sin título"


def clips_valorados(entradas, preferencias, identificador_clip, feedback_por_clip):
    """[{"ruta", "clip", "titulo", "estrellas", "stream", "fuente", "clip_id"}] de los clips valorados, mejores primero."""
    resultado = []
    for entrada in entradas:
        clip = dict(entrada.get("clip") or {})
        fuente = entrada.get("fuente")
        fb = feedback_por_clip(clip, fuente, preferencias)
        if fb is None and clip.get("clip_id_legado"):
            fb = next((f for f in reversed(preferencias.get("feedback", [])) if f.get("clip_id") == clip["clip_id_legado"]), None)
        n = estrellas_de(fb)
        if not n or not os.path.isfile(entrada["ruta_archivo"]):
            continue
        resultado.append({"ruta": entrada["ruta_archivo"], "clip": clip, "titulo": titulo_de(clip), "estrellas": n,
                          "stream": entrada.get("stream") or "", "fuente": fuente, "clip_id": identificador_clip(clip, fuente)})
    resultado.sort(key=lambda c: (-c["estrellas"], c["stream"], c["titulo"].lower()))
    return resultado


def cargar_exportados(ruta):
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def guardar_exportados(ruta, datos):
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    os.replace(temporal, ruta)


def clave_ruta(ruta):
    return os.path.normcase(os.path.abspath(ruta))


def crear_pestana_editar(contenedor, ctx):
    """``ctx``: catalogo_clips, cargar_preferencias, identificador_clip, feedback_por_clip, ruta_resultados(),
    generar_miniatura(archivo, destino), carpeta_cache (carpeta de la caché de revisión)."""
    marco = ttk.Frame(contenedor, padding=10)
    marco.columnconfigure(0, weight=1)
    marco.rowconfigure(2, weight=1)
    estado = tk.StringVar(value="")
    filtro = tk.StringVar(value=next(iter(FILTROS)))
    ttk.Label(marco, text="Editar", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
    fila = ttk.Frame(marco)
    fila.grid(row=1, column=0, sticky="ew", pady=(4, 8))
    ttk.Label(fila, text="Mostrar:").grid(row=0, column=0, padx=(0, 4))
    combo = ttk.Combobox(fila, textvariable=filtro, values=tuple(FILTROS), state="readonly", width=22)
    combo.grid(row=0, column=1)
    boton_actualizar = ttk.Button(fila, text="Actualizar")
    boton_actualizar.grid(row=0, column=2, padx=8)
    etiqueta_estado = ttk.Label(fila, textvariable=estado, wraplength=520, justify="left")
    etiqueta_estado.grid(row=0, column=3, sticky="w", padx=8)

    zona = ttk.Frame(marco)
    zona.grid(row=2, column=0, sticky="nsew")
    zona.columnconfigure(0, weight=1)
    zona.rowconfigure(0, weight=1)
    lienzo = tk.Canvas(zona, highlightthickness=0)
    barra = ttk.Scrollbar(zona, orient="vertical", command=lienzo.yview)
    contenido = ttk.Frame(lienzo)
    contenido.columnconfigure(0, weight=1)
    ventana = lienzo.create_window((0, 0), window=contenido, anchor="nw")
    lienzo.configure(yscrollcommand=barra.set)
    lienzo.grid(row=0, column=0, sticky="nsew")
    barra.grid(row=0, column=1, sticky="ns")
    contenido.bind("<Configure>", lambda _e: lienzo.configure(scrollregion=lienzo.bbox("all")))
    lienzo.bind("<Configure>", lambda e: lienzo.itemconfigure(ventana, width=e.width))
    marco.canvas_scroll = lienzo                      # la rueda del ratón de la ventana principal lo usa

    pool = ThreadPoolExecutor(max_workers=min(4, max(2, (os.cpu_count() or 2) // 2)))
    marco.bind("<Destroy>", lambda e: pool.shutdown(wait=False, cancel_futures=True) if e.widget is marco else None, add="+")
    miniaturas_listas, avisos = queue.SimpleQueue(), queue.SimpleQueue()
    tarjetas, todos, imagenes = [], [], {}
    firma = {"valor": None}
    exportados = {}
    ruta_exportados = {"valor": ""}
    paneles = {}

    def ruta_miniatura(c):
        ruta = c["ruta"]
        try:
            s = os.stat(ruta)
            version = f"{s.st_size}_{s.st_mtime_ns}"
        except OSError:
            version = "ausente"
        huella = (c["fuente"] or {}).get("fingerprint", "sin_fuente")
        return os.path.join(ctx["carpeta_cache"], huella, f"{c['clip_id']}_{version}_containfit_6fps_3s_v6.png")

    def pedir_miniatura(c, etiqueta):
        destino = ruta_miniatura(c)

        def tarea():
            try:
                ctx["generar_miniatura"](c["ruta"], destino)
            except Exception:
                pass
            miniaturas_listas.put((etiqueta, destino))
        if os.path.isfile(destino):
            miniaturas_listas.put((etiqueta, destino))
        else:
            pool.submit(tarea)

    def pintar_miniatura(etiqueta, destino):
        if not etiqueta.winfo_exists():
            return
        if os.path.isfile(destino):
            try:
                imagen = tk.PhotoImage(file=destino).subsample(REDUCCION_MINIATURA, REDUCCION_MINIATURA)
                imagenes[str(etiqueta)] = imagen
                etiqueta.configure(image=imagen, text="", width=0)
                return
            except tk.TclError:
                pass
        etiqueta.configure(text="Sin imagen")

    def drenar():
        if not marco.winfo_exists():
            return
        try:
            for _ in range(20):
                pintar_miniatura(*miniaturas_listas.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                mensaje, es_error = avisos.get_nowait()
                estado.set(mensaje)
                if es_error:
                    from tkinter import messagebox
                    messagebox.showerror("Editar", mensaje)
        except queue.Empty:
            pass
        marco.after(120, drenar)

    def abrir(c):
        estado.set("Abriendo el editor… (la primera vez prepara la vista previa del clip)")

        def tarea():
            ok, mensaje = editor_lanzador.abrir_editor(c["ruta"])
            avisos.put(("Editor abierto en el navegador." if ok else mensaje, not ok))
        threading.Thread(target=tarea, daemon=True, name="abrir-editor").start()

    def construir():
        for hijo in contenido.winfo_children():
            hijo.destroy()
        tarjetas.clear()
        minimo = FILTROS.get(filtro.get(), 1)
        visibles = [c for c in todos if c["estrellas"] >= minimo]
        if not visibles:
            texto = ("Aún no tienes clips valorados. Valora tus clips en «Validar clips» y aparecerán aquí para editarlos."
                     if not todos else "Ningún clip cumple ese filtro.")
            ttk.Label(contenido, text=texto, wraplength=520, justify="center").grid(row=0, column=0, pady=40)
            return
        pendientes = [c for c in visibles if clave_ruta(c["ruta"]) not in exportados]
        terminados = [c for c in visibles if clave_ruta(c["ruta"]) in exportados]
        fila = 0
        def encabezado(titulo, cantidad):
            nonlocal fila
            ttk.Label(contenido, text=f"{titulo} ({cantidad})", font=("Segoe UI", 11, "bold")).grid(row=fila, column=0, sticky="w", pady=(8, 3))
            fila += 1
        encabezado("Por editar", len(pendientes))
        paneles["pendientes"] = ttk.Frame(contenido); paneles["pendientes"].grid(row=fila, column=0, sticky="ew"); paneles["pendientes"].columnconfigure(0, weight=1); fila += 1
        encabezado("Editados", len(terminados))
        paneles["terminados"] = ttk.Frame(contenido); paneles["terminados"].grid(row=fila, column=0, sticky="ew"); paneles["terminados"].columnconfigure(0, weight=1)
        for grupo, lista in ((paneles["pendientes"], pendientes), (paneles["terminados"], terminados)):
          for numero, c in enumerate(lista):
            tarjeta = ttk.LabelFrame(grupo, padding=8)
            tarjeta.grid(row=numero, column=0, sticky="ew", padx=2, pady=3)
            tarjeta.columnconfigure(1, weight=1)
            marco_mini = ttk.Frame(tarjeta, relief="sunken")
            marco_mini.grid(row=0, column=0, sticky="nw", padx=(0, 12))
            etiqueta = ttk.Label(marco_mini, text="Cargando…", anchor="center", width=14)
            etiqueta.pack()
            ttk.Label(tarjeta, text=c["titulo"], font=("Segoe UI", 10, "bold"), wraplength=420, justify="left").grid(row=0, column=1, sticky="nw")
            ttk.Label(tarjeta, text=texto_estrellas(c["estrellas"]), font=("Segoe UI", 12)).grid(row=1, column=1, sticky="w", pady=(2, 0))
            if c["stream"]:
                ttk.Label(tarjeta, text=c["stream"]).grid(row=2, column=1, sticky="w")
            meta = exportados.get(clave_ruta(c["ruta"]), {})
            if meta.get("fecha"):
                ttk.Label(tarjeta, text=f"Editado: {meta['fecha']}").grid(row=3, column=1, sticky="w")
            ttk.Button(tarjeta, text="Editar", width=12, command=lambda c=c: abrir(c)).grid(row=0, column=2, rowspan=3, padx=(12, 4))
            ttk.Button(tarjeta, text="Marcar como por editar" if clave_ruta(c["ruta"]) in exportados else "Marcar como editado",
                       command=lambda c=c: alternar(c)).grid(row=3, column=2, padx=(12, 4))
            tarjetas.append(tarjeta)
            pedir_miniatura(c, etiqueta)

    def alternar(c, meta=None):
        k = clave_ruta(c["ruta"])
        if k in exportados and meta is None:
            exportados.pop(k, None)
        else:
            exportados[k] = meta or {"ruta_clip": c["ruta"], "fecha": datetime.now().astimezone().isoformat(timespec="minutes"), "salida": "", "manual": True}
        try: guardar_exportados(ruta_exportados["valor"], exportados)
        except OSError as exc: estado.set(f"No se pudo guardar exportados.json: {exc}")
        construir()

    def cargar(forzar=False):
        try:
            base = ctx["ruta_resultados"]()
            ruta_exportados["valor"] = os.path.join(base, "exportados.json")
            exportados.clear(); exportados.update(cargar_exportados(ruta_exportados["valor"]))
            entradas = [e for e in ctx["catalogo_clips"].cargar_catalogo(base) if os.path.isfile(e["ruta_archivo"])]
            prefs = ctx["cargar_preferencias"]()
            nuevos = clips_valorados(entradas, prefs, ctx["identificador_clip"], ctx["feedback_por_clip"])
        except Exception as exc:  # noqa: BLE001 - se muestra en la propia pestaña
            estado.set(f"No se pudieron leer los clips: {exc}")
            return
        huella = tuple((c["ruta"], c["estrellas"]) for c in nuevos)
        if not forzar and huella == firma["valor"]:
            return
        firma["valor"] = huella
        todos[:] = nuevos
        for c in nuevos:
            k = clave_ruta(c["ruta"])
            if k not in exportados:
                # Respaldo compatible con renders antiguos que no tenían registro.
                stem = os.path.splitext(os.path.basename(c["ruta"]))[0]
                carpeta = os.path.join(os.path.dirname(c["ruta"]), "editados")
                try: candidatos = [os.path.join(carpeta, n) for n in os.listdir(carpeta) if n.startswith(stem) and n.lower().endswith(".mp4")]
                except OSError: candidatos = []
                if candidatos:
                    salida = max(candidatos, key=os.path.getmtime)
                    exportados[k] = {"ruta_clip": c["ruta"], "fecha": datetime.fromtimestamp(os.path.getmtime(salida)).astimezone().isoformat(timespec="minutes"), "salida": salida}
        construir()
        estado.set(f"{len(nuevos)} clip(s) valorado(s). «Editar» abre el editor en tu navegador.")

    boton_actualizar.configure(command=lambda: cargar(forzar=True))
    combo.bind("<<ComboboxSelected>>", lambda _e: construir())
    marco.bind("<Map>", lambda e: cargar() if e.widget is marco else None, add="+")
    marco.after(120, drenar)
    return marco
