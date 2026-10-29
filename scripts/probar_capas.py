"""Prueba manual de las capas 1 y 4 sobre un transcript de ejemplo. NO llama a ninguna IA.

Ejecutar desde la carpeta scripts:   python probar_capas.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seleccion_capas as sc

# Parametros: los de configuracion_central.DEFAULTS (+ config.py si existe).
P = sc.cargar_parametros()

HABLA = [
    (0.0, 6.0, "Buenas buenas, bienvenidos al directo de hoy."),
    (6.5, 12.0, "Vamos a jugar Bomba Banana con Vicky y Hector."),
    (14.0, 19.0, "¿Pero qué hiciste?"),
    (19.5, 31.0, "No manches, pensé que estaba seguro y me di cuenta tarde de que la bomba estaba conmigo, jajaja!"),
    (31.5, 38.0, "Espera, espera, no puede ser."),
    (40.0, 52.0, "Perdí por un segundo, increíble lo que acaba de pasar en esa ronda tan reñida."),
    (52.5, 60.0, "Bueno, seguimos con la siguiente ronda y vemos qué pasa."),
    (75.0, 83.0, "Mira, mira, ahí viene!"),
]
PICOS = [(30.0, 33.0), (80.0, 82.0)]

linea_tiempo = [{"inicio": a, "fin": b, "texto": t, "tipo": "habla"} for a, b, t in HABLA]
linea_tiempo += [{"inicio": a, "fin": b, "texto": "REACCION FUERTE DE AUDIO DETECTADA", "tipo": "audio"} for a, b in PICOS]
linea_tiempo.sort(key=lambda x: x["inicio"])

print("=== CAPA 1: puntaje por linea ===")
lineas = sc.puntuar_lineas(linea_tiempo, P)
for l in lineas:
    print(f"{l['puntaje']:5.2f}  [{l['inicio']:5.1f}-{l['fin']:5.1f}]  {','.join(l['motivos']) or '-':40s} {l['texto'][:50]}")

print("\n=== Texto de pistas para el prompt (bloque 0-90 s) ===")
print(sc.pistas_para_prompt(lineas, 0, 90, P) or "(sin pistas)")

print("\n=== CAPA 4: validacion de candidatos de ejemplo ===")
anclas = sc.preparar_anclas(linea_tiempo)
candidatos = [
    {"tipo": "completo", "inicio": 14.4, "fin": 38.7, "titulo": "Se confunde con la bomba", "razon": "reaccion",
     "gancho": "😂 ¡No puede ser, la bomba conmigo! #gaming",
     "viralidad": {"gancho_puntaje": 22, "engagement_puntaje": 30, "valor_puntaje": 14,
                   "compartibilidad_puntaje": 18, "total": 99, "tipo_gancho": "Pregunta",
                   "razon_viralidad": "reaccion clara"}},
    {"tipo": "completo", "inicio": 40.0, "fin": 60.0, "titulo": "Pierde por un segundo", "razon": "payoff",
     "gancho": "Pierde", "viralidad": {"gancho_puntaje": 10}},
    {"tipo": "completo", "inicio": 44.0, "fin": 73.0, "titulo": "Limite lejano a lineas", "razon": "prueba"},
]
for c in candidatos:
    print("\nCandidato", c["inicio"], "-", c["fin"])
    r = sc.enriquecer_candidato(c, anclas, P, limites=(15, 90))
    print("  resultado:", json.dumps({k: r[k] for k in ("inicio", "fin", "gancho", "viralidad") if k in r}, ensure_ascii=False) if r else "DESCARTADO")

print("\nmezclar_score con peso 0 (por defecto): 62.5 ->", sc.mezclar_score(62.5, {"total": 80}, P))
print("mezclar_score con peso 0.3:", sc.mezclar_score(62.5, {"total": 80}, dict(P, PESO_VIRALIDAD_EN_SCORE=0.3)))
