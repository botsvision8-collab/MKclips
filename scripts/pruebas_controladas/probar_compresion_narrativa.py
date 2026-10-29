"""Pruebas sintéticas de Fase 2; no requieren Ollama ni FFmpeg."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from cache_mkclips import exigir_identidad_artefacto, guardar_identidad_artefacto
from narrativa_mkclips import comprimir_arco_narrativo, preparar_momento_independiente
from preferencias_mkclips import calcular_preferencia_usuario, cargar_preferencias, guardar_feedback
from verificar_segmentos import analizar_segmentos


def _linea(ventanas):
    return [{"inicio": a, "fin": b, "texto": texto, "tipo": "habla"} for a, b, texto in ventanas]


def _arco(fin=240):
    return {"id": "arco_1", "unidad_narrativa": "unidad_1", "inicio": 0, "fin": fin, "situacion": "puzzle", "objetivo": "resolver", "historia_completa": True}


def _clasificaciones(linea, etiquetas):
    return [{"inicio": x["inicio"], "fin": x["fin"], "clasificacion": etiqueta} for x, etiqueta in zip(linea, etiquetas)]


def ejecutar():
    # 1: independiente de 42s no se estira hasta el máximo.
    independiente = preparar_momento_independiente({"inicio": 10, "fin": 52, "tipo": "completo"}, [], 30, 120)
    assert independiente and independiente["duracion"] == 42 and independiente["tipo_candidato"] == "independiente"

    # 2: 18s agrega causa/reacción cercana y alcanza 31s.
    corto = preparar_momento_independiente({"inicio": 100, "fin": 118, "tipo": "corto"}, [{"inicio": 118, "fin": 131, "clasificacion": "RELEVANTE"}], 30, 120)
    assert corto and corto["duracion"] == 31

    # 3, 5, 6, 7, 8 y 9: arco de 240s comprimido, ventanas breves, silencio
    # narrativo conservado, diversidad y continuidad declarada.
    ventanas = [(0, 15, "Vamos a resolver el puzzle"), (40, 55, "aparece enemigo"), (80, 95, "dialogo importante de historia"), (120, 135, "jajaja comentario"), (160, 175, "descubre la llave"), (220, 235, "finalmente completamos el puzzle")]
    linea = _linea(ventanas); etiquetas = ["CONTEXTO", "RELEVANTE", "RELEVANTE", "COMICO", "SILENCIO_NARRATIVO", "RELEVANTE"]
    historia = comprimir_arco_narrativo(_arco(), _clasificaciones(linea, etiquetas), linea, 60, 120, 0.8)
    assert historia and 60 <= historia["duracion_final"] <= 120 and historia["duracion_original_arco"] == 240
    assert any(s["fin"] - s["inicio"] == 15 for s in historia["segmentos"])
    assert historia["compresion_narrativa"]["conserva_silencios_narrativos"] and historia["continuidad_visual"] == 0.8
    assert historia["cobertura_eventos"]["cantidad"] >= 3 and historia["densidad_cambios"] > 0
    assert all(p["motivo"] in {"inicio_frase_evento", "fin_frase_evento"} for p in historia["puntos_corte"])

    # 4: si la resolución indispensable no cabe, no se emite una historia rota.
    imposible_linea = _linea([(0, 75, "Vamos a resolver"), (165, 240, "finalmente completamos")])
    assert comprimir_arco_narrativo(_arco(), _clasificaciones(imposible_linea, ["CONTEXTO", "RELEVANTE"]), imposible_linea, 60, 120) is None

    # 10: ambas categorías coexisten en el pool sin conversión forzosa.
    pool = [dict(independiente, indice=i) for i in range(3)] + [dict(historia, indice=i) for i in range(2)]
    assert sum(x["tipo_candidato"] == "independiente" for x in pool) == 3 and sum(x["tipo_candidato"] == "historia" for x in pool) == 2

    # 11: nuevos atributos de compresión persisten y producen preferencia.
    ruta_pref = Path(__file__).with_name("_preferencias_fase2_test.json")
    try:
        ruta_pref.write_text('{"version": 1, "feedback": []}', encoding="utf-8")
        entrada = guardar_feedback(historia, 5, contexto_juego={"juego": "Zelda", "situacion": "puzzle"}, ruta=str(ruta_pref))
        datos = cargar_preferencias(str(ruta_pref))
        assert entrada["tipo_candidato"] == "historia" and entrada["cantidad_segmentos"] > 1
        assert calcular_preferencia_usuario(historia, {"juego": "Zelda", "situacion": "puzzle"}, datos)["muestras"] == 1
    finally:
        for ruta in (ruta_pref, Path(str(ruta_pref) + ".tmp")):
            if ruta.exists(): ruta.unlink()

    # 12: proveniencia rechaza una segunda fuente (usa vídeos reales si están disponibles).
    ruta_video = Path(__file__).with_name("_provenance_fase2_test_video.tmp")
    ruta_video.write_bytes(b"synthetic video for provenance test")
    ultimo = str(ruta_video)
    otro = ruta_video.with_name("otra_fuente.mkv")
    otro.write_bytes(b"different synthetic source")
    ruta_art = Path(__file__).with_name("_provenance_fase2_test.json")
    try:
        ruta_art.write_text("[]", encoding="utf-8")
        guardar_identidad_artefacto(str(ruta_art), ultimo, "fase2_test")
        exigir_identidad_artefacto(str(ruta_art), ultimo, "fase2_test")
        try:
            exigir_identidad_artefacto(str(ruta_art), str(otro), "fase2_test")
        except RuntimeError:
            pass
        else:
            raise AssertionError("La proveniencia aceptó otra fuente")
    finally:
        for ruta in (ruta_art, Path(str(ruta_art) + ".meta.json")):
            if ruta.exists(): ruta.unlink()
        if ruta_video.exists(): ruta_video.unlink()
        if otro.exists(): otro.unlink()

    # 13 y 14: contrato de duración por segmentos (incluye un tramo de 0.7s).
    compuesto = {"inicio": 0, "fin": 33, "segmentos": [{"inicio": 0, "fin": 0.7}, {"inicio": 10, "fin": 20}, {"inicio": 25, "fin": 45}]}
    datos_segmentos = analizar_segmentos(compuesto)
    assert abs(datos_segmentos["duracion_esperada"] - 30.7) < 0.001 and 30 <= datos_segmentos["duracion_esperada"] <= 120
    print("OK: 14 pruebas sintéticas de compresión narrativa")


if __name__ == "__main__":
    ejecutar()
