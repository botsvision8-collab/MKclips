"""Detecta material repetido aunque duración y manifiesto sean plausibles."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidencia_render import comprobar_correspondencia, registrar_render, verificar_render
from cache_mkclips import identidad_fuente
from preferencias_mkclips import guardar_feedback, cargar_preferencias, calcular_preferencia_usuario, feedback_por_clip


def video(ruta, colores):
    comando = ["ffmpeg", "-v", "error", "-y"]
    for color in colores:
        comando += ["-f", "lavfi", "-i", f"color=c={color}:s=128x72:r=30:d=1"]
    comando += ["-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-c:v", "libx264", str(ruta)]
    subprocess.run(comando, check=True, capture_output=True)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        fuente, repetido = base / "fuente.mkv", base / "repetido.mkv"
        video(fuente, ["red", "blue", "green"])
        video(repetido, ["red", "red", "green"])
        segmentos = [{"inicio": i, "fin": i + 1} for i in range(3)]
        comprobar_correspondencia(fuente, segmentos, fuente)
        try: comprobar_correspondencia(repetido, segmentos, fuente)
        except ValueError: pass
        else: raise AssertionError("No detectó concatenación duplicada con duración correcta")
        registrar_render(repetido, fuente, segmentos)
        contrato = Path(str(repetido) + ".render.json")
        datos = json.loads(contrato.read_text(encoding="utf-8")); datos["sha256"] = "incorrecto"
        contrato.write_text(json.dumps(datos), encoding="utf-8")
        try: verificar_render(repetido, segmentos, identidad_fuente(fuente))
        except ValueError: pass
        else: raise AssertionError("Aceptó bytes distintos al contrato")
        ruta = str(base / "feedback.json")
        clip = {"titulo": "Prueba", "inicio": 0, "fin": 3, "tipo_candidato": "historia"}
        identidad = {"fingerprint": "stream_A"}
        guardar_feedback(clip, rating=5, fuente=identidad, ruta=ruta)
        assert feedback_por_clip(clip, {"fingerprint": "stream_B"}, cargar_preferencias(ruta)) is None
        guardar_feedback(clip, fuente=identidad, ruta=ruta)
        assert calcular_preferencia_usuario(clip, {}, cargar_preferencias(ruta))["muestras"] == 0
    print("OK: muestreo positivo, duplicación física negativa, hash alterado, feedback entre streams y retirada de valoración.")


if __name__ == "__main__": main()
