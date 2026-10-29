import json
import os
from datetime import datetime

ARCHIVO_HISTORIAL = "historial_clips.json"
ARCHIVO_RESULTADOS = "resultados_reales.json"

def cargar_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def guardar_json(path, datos):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

historial = cargar_json(ARCHIVO_HISTORIAL)

if not historial:
    print("No hay ningún clip en el historial todavía. Corre primero cortar_clips.py al menos una vez.")
    exit()

# Mostrar solo los que aun no se han registrado, mas recientes primero
pendientes = [h for h in historial if not h.get("registrado", False)]
pendientes = list(reversed(pendientes))[:20]  # los 20 mas recientes sin registrar

if not pendientes:
    print("Todos los clips del historial ya tienen resultados registrados.")
    print("Si quieres registrar uno de nuevo, borra manualmente 'registrado: true' en historial_clips.json")
    exit()

print("=== Elige el clip al que le vas a registrar resultados ===\n")
for idx, h in enumerate(pendientes, start=1):
    print(f"{idx}. [{h['stream']}] \"{h['titulo']}\" - {h.get('razon','')}")

print()
while True:
    seleccion = input("Numero del clip (o 'salir'): ").strip()
    if seleccion.lower() == "salir":
        exit()
    if seleccion.isdigit() and 1 <= int(seleccion) <= len(pendientes):
        elegido = pendientes[int(seleccion) - 1]
        break
    print("  Numero invalido, intenta de nuevo.")

print(f"\nRegistrando resultados para: \"{elegido['titulo']}\"\n")

def pedir_numero(campo):
    while True:
        valor = input(f"{campo}: ").strip().replace(",", "").replace(".", "")
        if valor.isdigit():
            return int(valor)
        print("  Por favor ingresa solo numeros (ej: 15000).")

vistas = pedir_numero("Vistas")
likes = pedir_numero("Likes")
comentarios = pedir_numero("Comentarios")
compartidos = pedir_numero("Compartidos")

resultados = cargar_json(ARCHIVO_RESULTADOS)
resultados.append({
    "titulo": elegido["titulo"],
    "razon": elegido.get("razon", ""),
    "archivo": elegido.get("archivo", ""),
    "stream": elegido.get("stream", ""),
    "vistas": vistas,
    "likes": likes,
    "comentarios": comentarios,
    "compartidos": compartidos,
    "fecha_registro": datetime.now().strftime("%Y-%m-%d")
})
guardar_json(ARCHIVO_RESULTADOS, resultados)

# Marcar como registrado en el historial para que no vuelva a aparecer en la lista
for h in historial:
    if h.get("archivo") == elegido.get("archivo") and h.get("stream") == elegido.get("stream"):
        h["registrado"] = True
        break
guardar_json(ARCHIVO_HISTORIAL, historial)

print(f"\nGuardado. Ahora tienes {len(resultados)} clips con resultados reales registrados.")

resultados_ordenados = sorted(resultados, key=lambda x: x["vistas"], reverse=True)
print("\nTop clips por vistas hasta ahora:")
for r in resultados_ordenados[:5]:
    print(f"  {r['vistas']:>8} vistas - \"{r['titulo']}\"")