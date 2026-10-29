"""Prueba aislada del contrato de segmentos compuestos de MKClips.

No toca scripts/resultados ni la carpeta configurada de clips. Ejecuta las
funciones operativas del cutter desde su fuente y valida la salida con el
verificador operativo usando directorios propios bajo pruebas_controladas.
"""

import ast
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = BASE_DIR.parent
VIDEO = Path(sys.argv[1]).resolve()
SALIDA_DIR = BASE_DIR / "salida_segmentos_compuestos"
RESULTADOS_DIR = BASE_DIR / "resultados_segmentos_compuestos"
SEGMENTOS = [
    {"inicio": 100.0, "fin": 120.0},
    {"inicio": 145.0, "fin": 170.0},
    {"inicio": 185.0, "fin": 200.0},
]
ESPERADO = sum(segmento["fin"] - segmento["inicio"] for segmento in SEGMENTOS)


def _cargar_funciones_cutter():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    fuente = (SCRIPTS_DIR / "cortar_clips_nvenc.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    requeridas = {
        "construir_filtro_multipista",
        "_args_video_nvenc",
        "_ejecutar_ffmpeg",
        "cortar_por_segmentos",
    }
    funciones = [nodo for nodo in arbol.body if isinstance(nodo, ast.FunctionDef) and nodo.name in requeridas]
    modulo = ast.Module(body=funciones, type_ignores=[])
    espacio = {
        "normalizar_segmentos_sin_duplicados": __import__("narrativa_mkclips").normalizar_segmentos_sin_duplicados,
        "DURACION_MIN_CLIP": 60, "DURACION_MAX_CLIP": 90,
        "os": os,
        "subprocess": subprocess,
        "hardware_scheduler": __import__("hardware_scheduler"),
        "NVENC_ENCODER": "h264_nvenc",
        "NVENC_PRESET": "p5",
        "NVENC_CQ": "21",
        "NVENC_AUDIO": "aac",
        "todos_los_segmentos": [],
    }
    exec(compile(modulo, str(SCRIPTS_DIR / "cortar_clips_nvenc.py"), "exec"), espacio)
    return espacio


def _pistas_audio(video):
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(video)],
        capture_output=True,
        text=True,
        check=False,
    )
    return max(1, len([linea for linea in resultado.stdout.splitlines() if linea.strip()]))


def _duracion(video):
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(resultado.stdout.strip())


def main():
    if not VIDEO.is_file():
        raise FileNotFoundError(VIDEO)
    SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    salida = SALIDA_DIR / "clip_compuesto_100_200.mkv"

    cutter = _cargar_funciones_cutter()
    # MIN/MAX se aplica al total único, nunca a cada segmento interno.
    for invalidos in ([{"inicio": 100, "fin": 120}] * 4, [{"inicio": 100, "fin": 200}]):
        rechazo, _ = cutter["cortar_por_segmentos"](str(VIDEO), invalidos, str(SALIDA_DIR / "no_debe_existir.mkv"), _pistas_audio(VIDEO))
        assert rechazo == -1, "NVENC aceptó duración normalizada fuera de MIN/MAX"
    resultado, rangos = cutter["cortar_por_segmentos"](
        str(VIDEO), SEGMENTOS + [dict(SEGMENTOS[0])], str(salida), _pistas_audio(VIDEO)
    )
    if resultado < 0 or not salida.is_file():
        raise RuntimeError("El cutter no pudo renderizar el clip compuesto.")

    clips = [{
        "tipo": "completo",
        "titulo": "Prueba controlada de segmentos",
        "inicio": SEGMENTOS[0]["inicio"],
        "fin": SEGMENTOS[-1]["fin"],
        "segmentos": SEGMENTOS,
        "archivo": str(salida),
    }]
    (RESULTADOS_DIR / "clips_sugeridos.json").write_text(
        json.dumps(clips, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    from cache_mkclips import guardar_identidad_artefacto
    from evidencia_render import registrar_render
    guardar_identidad_artefacto(str(RESULTADOS_DIR / "clips_sugeridos.json"), str(VIDEO), "clips_sugeridos")
    registrar_render(salida, str(VIDEO), SEGMENTOS)

    os.environ["MKCLIPS_RESULTADOS_DIR"] = str(RESULTADOS_DIR)
    os.environ["MKCLIPS_CLIPS_DIR"] = str(SALIDA_DIR)
    especificacion = importlib.util.spec_from_file_location(
        "verificar_segmentos_controlado", SCRIPTS_DIR / "verificar_segmentos.py"
    )
    verificador = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(verificador)
    estado = verificador.main()

    real = _duracion(salida)
    print(f"Duración esperada: {ESPERADO:.3f}s")
    print(f"Duración ffprobe:  {real:.3f}s")
    print(f"Rangos renderizados: {rangos}")
    if estado != 0 or abs(real - ESPERADO) > verificador.TOLERANCIA_SEGUNDOS:
        raise RuntimeError("La duración del compuesto no coincide con la suma contractual.")


if __name__ == "__main__":
    main()
