"""Etapa de transcripcion cuando TRANSCRIPCION_MOTOR = "assemblyai".

Escribe transcripcion.json (+ meta) igual que transcribir.py. Si AssemblyAI falla por cualquier
motivo, ejecuta transcribir.py (Whisper local) para que el proceso nunca se rompa.
Lo lanza procesar_multiples.correr_paso en lugar de transcribir.py.
"""
import json
import os
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    from rutas_app import datos_dir
except ImportError:
    from .rutas_app import datos_dir
BASE_DIR = str(datos_dir())
os.chdir(BASE_DIR)
sys.path.insert(0, SCRIPT_DIR)
try:
    from rutas_app import comando_python
except ImportError:
    from .rutas_app import comando_python


def _whisper_local():
    print("Usando Whisper local en su lugar...")
    codigo = subprocess.run(comando_python("transcribir.py", sys.argv[1:]), cwd=BASE_DIR).returncode
    sys.exit(codigo)


def _main():
    try:
        import transcribir  # solo definiciones; no ejecuta nada al importarse
        import procesar_multiples
        import transcripcion_assemblyai as asm
        from cache_mkclips import ensure_audio_cache, guardar_identidad_artefacto
    except Exception as exc:
        print(f"No se pudo preparar AssemblyAI ({exc}).")
        _whisper_local()

    video_path = transcribir.resolver_video_path(sys.argv[1] if len(sys.argv) > 1 else None)
    nombre_video = os.path.splitext(os.path.basename(video_path))[0]
    print(f"\nVideo seleccionado: {video_path}\nMotor de transcripcion: AssemblyAI (nube)\n")
    with open("ultimo_video.txt", "w", encoding="utf-8") as f:
        f.write(video_path + "\n" + nombre_video)

    t0 = time.time()
    try:
        audio = ensure_audio_cache(video_path, notificar=print)
        resultado = asm.transcribir(
            audio, correcciones=transcribir.CORRECCIONES, notificar=print,
            progreso=procesar_multiples.actualizar_porcentaje_progreso)
        if not resultado:
            raise asm.ErrorAssemblyAI("AssemblyAI devolvio una transcripcion vacia.")
    except Exception as exc:
        print(f"AssemblyAI no esta disponible ({exc}).")
        _whisper_local()

    print(f"\nTranscripcion terminada en {time.time() - t0:.0f}s.")
    with open("transcripcion.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    guardar_identidad_artefacto("transcripcion.json", video_path, "transcripcion")
    print(f"\nListo. {len(resultado)} segmentos guardados en transcripcion.json\nVideo procesado: {nombre_video}")


if __name__ == "__main__":
    _main()
