# -*- coding: utf-8 -*-
"""Pruebas controladas de segmentos para evitar repeticiones en render."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrativa_mkclips import normalizar_segmentos_sin_duplicados


def rangos(segmentos):
    return [(s["inicio"], s["fin"]) for s in segmentos]


CASOS = (
    ("instantes independientes próximos", [{"inicio": 100, "fin": 100.1}, {"inicio": 100.2, "fin": 100.3}], [(100., 100.1), (100.2, 100.3)]),
    ("solapamiento fuerte", [{"inicio": 100, "fin": 115}, {"inicio": 110, "fin": 125}], [(100., 125.)]),
    ("mismo evento fases distintas", [{"inicio": 100, "fin": 110, "evento_id": "jefe", "rol_narrativo": "setup"}, {"inicio": 115, "fin": 125, "evento_id": "jefe", "rol_narrativo": "resolucion"}], [(100., 110.), (115., 125.)]),
    ("duplicado exacto", [{"inicio": 10, "fin": 25}, {"inicio": 40, "fin": 55}, {"inicio": 10, "fin": 25}], [(10.0, 25.0), (40.0, 55.0)]),
    ("casi idéntico", [{"inicio": 10.0, "fin": 25.0}, {"inicio": 10.2, "fin": 24.9}], [(10.0, 25.0)]),
    ("contenido", [{"inicio": 10, "fin": 30}, {"inicio": 15, "fin": 25}], [(10.0, 30.0)]),
    ("independientes", [{"inicio": 10, "fin": 20}, {"inicio": 40, "fin": 50}], [(10.0, 20.0), (40.0, 50.0)]),
    ("historia legítima", [{"inicio": 10, "fin": 20}, {"inicio": 30, "fin": 40}, {"inicio": 50, "fin": 65}, {"inicio": 80, "fin": 95}], [(10.0, 20.0), (30.0, 40.0), (50.0, 65.0), (80.0, 95.0)]),
    ("mismo evento declarado", [{"inicio": 10, "fin": 25, "evento_id": "puzzle_final"}, {"inicio": 80, "fin": 95, "evento_id": "puzzle_final"}], [(10.0, 25.0)]),
)


for nombre, entrada, esperado in CASOS:
    obtenido = rangos(normalizar_segmentos_sin_duplicados(entrada))
    assert obtenido == esperado, f"{nombre}: {obtenido!r} != {esperado!r}"
    print(f"OK: {nombre}")
