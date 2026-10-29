import json
import os

ARCHIVO_EJEMPLOS = "ejemplos_buenos.json"

def cargar_ejemplos():
    if os.path.exists(ARCHIVO_EJEMPLOS):
        with open(ARCHIVO_EJEMPLOS, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def guardar_ejemplos(ejemplos):
    with open(ARCHIVO_EJEMPLOS, "w", encoding="utf-8") as f:
        json.dump(ejemplos, f, ensure_ascii=False, indent=2)

print("=== Agregar ejemplo de momento gracioso confirmado ===")
print("(Esto ayuda a que la IA aprenda tu sentido del humor especifico)\n")

texto = input("Pega o describe brevemente lo que se dijo/paso en ese momento: ").strip()
razon = input("¿Por que fue gracioso? (breve, en tus palabras): ").strip()

if not texto or not razon:
    print("\nNo se guardo nada, faltan datos.")
else:
    ejemplos = cargar_ejemplos()
    ejemplos.append({"texto": texto, "razon": razon})
    guardar_ejemplos(ejemplos)
    print(f"\nGuardado. Ahora tienes {len(ejemplos)} ejemplos confirmados en {ARCHIVO_EJEMPLOS}.")