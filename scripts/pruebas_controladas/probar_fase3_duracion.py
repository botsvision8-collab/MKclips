"""Pruebas deterministas de Fase 3; no ejecuta Whisper, OBS, NVENC ni Ollama."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import cache_mkclips
import configuracion_central
import panel_grabacion
import procesar_multiples
from duracion_clips import ajustar_a_limites_narrativos, validar_limites_duracion


def prueba_configuracion_y_paneles(tmp: Path):
    ruta = tmp / "config.py"
    ruta.write_text("EXTRA = 'se conserva'\n", encoding="utf-8")
    configuracion_central.ruta_configuracion = lambda: ruta

    valores = configuracion_central.leer_configuracion()
    assert valores["DURACION_MIN_CLIP"] == valores["DURACION_MAX_CLIP"] == 0
    configuracion_central.guardar_configuracion(valores)
    assert "EXTRA = 'se conserva'" in ruta.read_text(encoding="utf-8")

    valores.update(DURACION_MIN_CLIP=15, DURACION_MAX_CLIP=90)
    configuracion_central.guardar_configuracion(valores)
    leida = configuracion_central.leer_configuracion()
    assert (leida["DURACION_MIN_CLIP"], leida["DURACION_MAX_CLIP"]) == (15, 90)
    import configuracion_app
    assert configuracion_app.guardar_configuracion is configuracion_central.guardar_configuracion

    for invalido in ((-1, 0), (0, -1), (60, 30), ("x", 0)):
        try:
            validar_limites_duracion(*invalido)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Se aceptó límite inválido: {invalido}")


def prueba_limites_narrativos():
    unidades = [{"id": 1, "inicio": 0, "fin": 60}]
    candidato = {"unidad_narrativa": "unidad_1", "inicio": 20, "fin": 40, "provenance": {"origen": "prueba"}}
    # 0/0 no altera el comportamiento ni la identidad del candidato.
    assert ajustar_a_limites_narrativos(candidato, unidades, 0, 0) is candidato
    ampliado = ajustar_a_limites_narrativos(candidato, unidades, 50, 70)
    assert ampliado["inicio"] == 0 and ampliado["fin"] == 60
    assert ampliado["provenance"] == candidato["provenance"]
    # No se corta una unidad para cumplir un máximo.
    assert ajustar_a_limites_narrativos(ampliado, unidades, 0, 30) is None

    compuesto = {
        "unidad_narrativa": "unidad_1", "inicio": 0, "fin": 50,
        "segmentos": [{"inicio": 0, "fin": 15}, {"inicio": 35, "fin": 50}],
        "provenance": {"origen": "prueba"},
    }
    preservado = ajustar_a_limites_narrativos(compuesto, unidades, 20, 40)
    assert preservado is compuesto and preservado["segmentos"] == compuesto["segmentos"]
    assert preservado["provenance"] == compuesto["provenance"]
    # Contrato JSON final: segmentos, inicio, fin y duración coherentes.
    final = dict(preservado)
    final["duracion"] = sum(s["fin"] - s["inicio"] for s in final["segmentos"])
    assert final["inicio"] == final["segmentos"][0]["inicio"]
    assert final["fin"] == final["segmentos"][-1]["fin"]
    assert json.loads(json.dumps([final]))[0]["segmentos"]


def prueba_cache_y_reanudacion(tmp: Path):
    # Dependencias: min/max solo cambia identificación.
    original_digest = procesar_multiples._digest_archivo
    original_valores = procesar_multiples._valores_configuracion
    original_resultados = procesar_multiples.RESULTADOS_DIR
    limites = {"DURACION_MIN_CLIP": 0, "DURACION_MAX_CLIP": 0}
    procesar_multiples._digest_archivo = lambda ruta: f"digest:{Path(ruta).name}"
    procesar_multiples._valores_configuracion = lambda claves: {k: limites.get(k) for k in claves}
    procesar_multiples.RESULTADOS_DIR = str(tmp)
    try:
        transcripcion_1 = procesar_multiples._dependencias_cache("video", "transcripcion")
        audio_1 = procesar_multiples._dependencias_cache("video", "eventos_audio")
        visual_1 = procesar_multiples._dependencias_cache("video", "eventos_visuales")
        identificacion_1 = procesar_multiples._dependencias_cache("video", "identificacion")
        limites["DURACION_MAX_CLIP"] = 75
        transcripcion_2 = procesar_multiples._dependencias_cache("video", "transcripcion")
        audio_2 = procesar_multiples._dependencias_cache("video", "eventos_audio")
        visual_2 = procesar_multiples._dependencias_cache("video", "eventos_visuales")
        identificacion_2 = procesar_multiples._dependencias_cache("video", "identificacion")
        assert transcripcion_1 == transcripcion_2
        assert audio_1 == audio_2 and visual_1 == visual_2
        assert identificacion_1 != identificacion_2

        # El validador de caché confirma HIT con mismas dependencias y MISS al cambiar límites.
        video = tmp / "video.bin"
        artefacto = tmp / "candidatos_todos.json"
        video.write_bytes(b"video de prueba")
        artefacto.write_text("[]", encoding="utf-8")
        cache_mkclips.CACHE_ROOT = str(tmp / "cache")
        cache_mkclips.STAGE_CACHE_DIR = str(tmp / "cache" / "stages")
        deps = {"duracion_clips": {"minimo": 0, "maximo": 75}}
        assert cache_mkclips.guardar_cache_etapa(str(video), "identificacion", [str(artefacto)], deps)
        assert cache_mkclips.validar_cache_etapa(str(video), "identificacion", [str(artefacto)], deps)
        assert not cache_mkclips.validar_cache_etapa(
            str(video), "identificacion", [str(artefacto)],
            {"duracion_clips": {"minimo": 0, "maximo": 76}},
        )
    finally:
        procesar_multiples._digest_archivo = original_digest
        procesar_multiples._valores_configuracion = original_valores
        procesar_multiples.RESULTADOS_DIR = original_resultados

    # Reanudar guarda caché después de una etapa correcta (antes era inalcanzable).
    original = {
        "leer": procesar_multiples.leer_estado_progreso,
        "pasos": procesar_multiples.PASOS_PIPELINE,
        "streams": procesar_multiples.CARPETA_STREAMS,
        "cache": procesar_multiples._intentar_cache_etapa,
        "correr": procesar_multiples.correr_paso,
        "guardar": procesar_multiples._guardar_cache_etapa,
        "estado": procesar_multiples._escribir_estado_progreso,
        "metricas": procesar_multiples._registrar_metrica_paso,
        "notificacion": procesar_multiples.lanzar_notificacion_progreso,
    }
    guardados = []
    (tmp / "stream.mkv").write_bytes(b"x")
    try:
        procesar_multiples.leer_estado_progreso = lambda: {"archivo": "stream.mkv", "paso_actual": 1, "terminado": False}
        procesar_multiples.PASOS_PIPELINE = [("etapa.py", False, "Prueba")]
        procesar_multiples.CARPETA_STREAMS = str(tmp)
        procesar_multiples._intentar_cache_etapa = lambda *args: False
        procesar_multiples.correr_paso = lambda *args: (True, 0.01)
        procesar_multiples._guardar_cache_etapa = lambda video, paso: guardados.append((video, paso))
        procesar_multiples._escribir_estado_progreso = lambda *args, **kwargs: None
        procesar_multiples._registrar_metrica_paso = lambda *args: None
        procesar_multiples.lanzar_notificacion_progreso = lambda: None
        assert procesar_multiples.reanudar_ultimo_proceso(notificar=lambda _: None)
        assert guardados and guardados[0][1] == "etapa.py"
    finally:
        procesar_multiples.leer_estado_progreso = original["leer"]
        procesar_multiples.PASOS_PIPELINE = original["pasos"]
        procesar_multiples.CARPETA_STREAMS = original["streams"]
        procesar_multiples._intentar_cache_etapa = original["cache"]
        procesar_multiples.correr_paso = original["correr"]
        procesar_multiples._guardar_cache_etapa = original["guardar"]
        procesar_multiples._escribir_estado_progreso = original["estado"]
        procesar_multiples._registrar_metrica_paso = original["metricas"]
        procesar_multiples.lanzar_notificacion_progreso = original["notificacion"]


def main():
    with tempfile.TemporaryDirectory(prefix="mkclips_fase3_") as temporal:
        tmp = Path(temporal)
        prueba_configuracion_y_paneles(tmp)
        prueba_limites_narrativos()
        prueba_cache_y_reanudacion(tmp)
    print("Fase 3: todas las pruebas deterministas pasaron.")


if __name__ == "__main__":
    main()
