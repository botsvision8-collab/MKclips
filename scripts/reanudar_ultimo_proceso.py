"""
reanudar_ultimo_proceso.py - Si el ultimo proceso se quedo a medias (se
cerro la ventana, se mato el proceso, fallo un paso), esto lo retoma
desde el paso exacto donde se quedo, sin repetir lo que ya estaba hecho.

Uso: python reanudar_ultimo_proceso.py
"""

import procesar_multiples


def main():
    resultado = procesar_multiples.reanudar_ultimo_proceso(notificar=print)
    if resultado is None:
        print("\nNada que reanudar.")
    elif resultado:
        print("\nListo, se reanudo y termino bien.")
    else:
        print("\nFallo al reanudar. Revisa el error de arriba.")


if __name__ == "__main__":
    main()
