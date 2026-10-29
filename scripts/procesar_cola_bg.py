"""
procesar_cola_bg.py - Corre una cola de videos de forma INDEPENDIENTE de
configuracion_app.py. Pensado para lanzarse en su propia consola separada
(CREATE_NEW_CONSOLE), asi que si cerras la app, esto sigue corriendo solo.

Uso: python procesar_cola_bg.py <manifiesto.json>

El manifiesto es una lista de {"path": "...", "es_descarga": bool}.
"""

import sys
import os
import json
import time

import procesar_multiples


def main():
    if len(sys.argv) < 2:
        print("Uso: python procesar_cola_bg.py <manifiesto.json>")
        sys.exit(1)

    ruta_manifiesto = sys.argv[1]
    with open(ruta_manifiesto, "r", encoding="utf-8") as f:
        cola = json.load(f)

    if not cola:
        print("La cola esta vacia, nada que hacer.")
        return

    print(f"=== Procesando {len(cola)} video(s) en segundo plano ===")
    print("Esta ventana es independiente de la app - podes cerrar la app sin problema,\n"
          "esto va a seguir corriendo hasta terminar.\n")

    for i, item in enumerate(cola, start=1):
        ruta = item["path"]
        es_descarga = item.get("es_descarga", False)
        nombre = os.path.basename(ruta)
        print(f"\n{'='*60}\n {i}/{len(cola)}: {nombre}\n{'='*60}\n")

        ok = procesar_multiples.procesar_un_video(ruta, modo_automatico=True, notificar=print)

        if ok and es_descarga:
            try:
                os.remove(ruta)
                print(f"Video descargado eliminado: {nombre}")
            except OSError as e:
                print(f"No se pudo borrar el video descargado: {e}")

    try:
        os.remove(ruta_manifiesto)
    except OSError:
        pass

    print("\n=== Cola completa ===")
    print("Esta ventana se puede cerrar.")
    time.sleep(5)


if __name__ == "__main__":
    main()
