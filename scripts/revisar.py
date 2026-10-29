import json

with open("transcripcion.json", encoding="utf-8") as f:
    d = json.load(f)

print(f"{len(d)} segmentos")
print(f"Desde el segundo {d[0]['inicio']} hasta {d[-1]['fin']}")
print(f"Duración cubierta: {d[-1]['fin'] / 60:.1f} minutos")
