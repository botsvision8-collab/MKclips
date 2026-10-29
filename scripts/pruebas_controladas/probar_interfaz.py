"""Prueba Tk real; feedback y tema de prueba quedan aislados del usuario."""
from pathlib import Path
import json
import sys
import tempfile
import traceback
import time
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import configuracion_app as app
import interfaz_mkclips as ui
import preferencias_mkclips as prefs

SALIDA = Path(__file__).resolve().parents[2] / "validacion_20260920"


def ejecutar():
    errores = []
    metricas = {}
    with tempfile.TemporaryDirectory() as temporal:
        ruta = str(Path(temporal) / "preferencias.json")
        ui.RUTA_TEMA = Path(temporal) / "tema.json"
        app.cargar_preferencias = lambda: prefs.cargar_preferencias(ruta)
        app.guardar_feedback = lambda clip, **kw: prefs.guardar_feedback(clip, ruta=ruta, **kw)
        app.messagebox.showinfo = lambda *a: None
        app.messagebox.showerror = lambda *a: errores.append(str(a))
        root = app.crear_ventana()
        root.geometry("1180x820+20+20")
        root.report_callback_exception = lambda *a: errores.append(str(a))

        def widgets(w):
            yield w
            for h in w.winfo_children(): yield from widgets(h)

        def boton(texto):
            return next(w for w in widgets(root) if isinstance(w, ttk.Button) and w.cget("text") == texto)

        def paso1():
            try:
                assert not any(isinstance(w, tk.Toplevel) for w in widgets(root))
                assert not any("Referencias" in str(w.cget("text")) for w in widgets(root) if "text" in w.keys())
                for nombre in ("Configuración", "Flujo de trabajo", "Validar clips"):
                    boton(nombre).invoke(); root.update_idletasks()
                inicio = time.perf_counter()
                boton("Cargar resultados").invoke()
                metricas["carga_datos_provenance_y_tarjetas_segundos"] = round(time.perf_counter() - inicio, 3)
                ui.aplicar_tema(root, "Modo oscuro", guardar=True)
                assert ui.leer_tema() == "Modo oscuro"
                root.after(4500, paso2)
            except Exception as e: errores.append(traceback.format_exc()); terminar()

        def paso2():
            try:
                from PIL import ImageGrab
                ImageGrab.grab(bbox=(root.winfo_rootx(), root.winfo_rooty(), root.winfo_rootx()+root.winfo_width(), root.winfo_rooty()+root.winfo_height())).save(SALIDA / "ui_oscuro.png")
                boton("☆").invoke(); boton("Guardar valoraciones").invoke()
                feedback = prefs.cargar_preferencias(ruta)["feedback"]
                assert feedback[-1]["rating"] == 1
                assert any(w.cget("text") == "★" for w in widgets(root) if isinstance(w, ttk.Button))
                ayuda = next(w for w in widgets(root) if isinstance(w, ttk.Label) and str(w.cget("cursor")) == "question_arrow")
                ayuda.event_generate("<Enter>")
                assert any(isinstance(w, ttk.Label) and w.winfo_manager() == "place" for w in root.winfo_children())
                ayuda.event_generate("<Leave>")
                combos = [w for w in widgets(root) if isinstance(w, ttk.Combobox)]
                for w in combos:
                    if "Historias" in w.cget("values"):
                        w.set("Historias"); w.event_generate("<<ComboboxSelected>>")
                        w.set("Momentos"); w.set("Todos")
                root.after(1500, probar_hover)
            except Exception as e: errores.append(traceback.format_exc()); terminar()

        def probar_hover():
            try:
                mini = next(w for w in widgets(root) if isinstance(w, ttk.Label) and str(w.cget("cursor")) == "hand2")
                assert mini.cget("image"), "Miniatura visible no generada"
                mini.event_generate("<Enter>")
                root.mini_prueba = mini
                root.imagen_inicial = str(mini.cget("image"))
                root.after(5000, paso3)
            except Exception: errores.append(traceback.format_exc()); terminar()

        def paso3():
            try:
                assert str(root.mini_prueba.cget("image")) != root.imagen_inicial, "Hover no animó el preview"
                selector = next(w for w in widgets(root) if isinstance(w, ttk.Combobox) and "Modo claro" in w.cget("values"))
                selector.set("Modo claro"); selector.event_generate("<<ComboboxSelected>>")
                assert ui.leer_tema() == "Modo claro"
                root.update_idletasks()
                from PIL import ImageGrab
                ImageGrab.grab(bbox=(root.winfo_rootx(), root.winfo_rooty(), root.winfo_rootx()+root.winfo_width(), root.winfo_rooty()+root.winfo_height())).save(SALIDA / "ui_claro.png")
                assert not any(isinstance(w, tk.Toplevel) for w in widgets(root))
            except Exception as e: errores.append(repr(e))
            terminar()

        def terminar():
            root.destroy()

        root.after(300, paso1)
        root.mainloop()
    (SALIDA / "ui_pruebas.json").write_text(json.dumps({"errores": errores, "metricas": metricas}, ensure_ascii=False, indent=2), encoding="utf-8")
    assert not errores, errores
    print("OK: Tk, navegación, temas persistidos, miniatura, hover animado, tooltips internos, filtros, estrellas, guardar/recuperar feedback aislado; sin Toplevel.")


if __name__ == "__main__": ejecutar()
