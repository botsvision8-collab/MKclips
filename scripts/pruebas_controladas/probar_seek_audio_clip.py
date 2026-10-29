"""Regresión: los cortes de audio del clip usan atrim para conservar señal en este MKV."""
from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

try:
    from scripts import editor_render_piezas as rp
except ImportError:
    import editor_render_piezas as rp


CLIP = Path(os.environ.get("MKCLIPS_TEST_CLIP", Path(__file__).with_name("clip_21.mkv")))


@unittest.skipUnless(CLIP.is_file(), "requiere el MKV real usado para reproducir clip_21")
class SeekAudioClipRegression(unittest.TestCase):
    def test_plan_recorta_audio_del_clip_dentro_del_filtro(self):
        edicion = {
            "clip": str(CLIP),
            "origen": {"pistas_audio": 1, "fps": 30},
            "salida": {"ancho": 1080, "alto": 1920},
            "subtitulos": {"activos": False, "lineas": []},
            "pistas": {},
            "extras": [],
            "segmentos": [],
            "piezas": [{
                "id": "a1", "tipo": "audio", "fuente": "clip", "archivo": "",
                "carril": "A1", "t": 0.0, "desde": 2.733, "dur": 5.567,
                "velocidad": 1.0, "volumen": 1.0, "fundido_in": 0.0,
                "fundido_out": 0.0, "kf": {},
            }],
        }
        plan = rp.planificar(edicion, solo_audio=True)
        self.assertEqual(plan["entradas"], ["-i", str(CLIP)])
        self.assertIn("atrim=start=2.733:duration=5.567", plan["filtro"])

    def test_recorte_de_audio_con_el_plan_tiene_senal(self):
        edicion = {
            "clip": str(CLIP),
            "origen": {"pistas_audio": 1, "fps": 30},
            "salida": {"ancho": 1080, "alto": 1920},
            "subtitulos": {"activos": False, "lineas": []},
            "pistas": {},
            "extras": [],
            "segmentos": [],
            "piezas": [{
                "id": "a1", "tipo": "audio", "fuente": "clip", "archivo": "",
                "carril": "A1", "t": 0.0, "desde": 2.733, "dur": 5.567,
                "velocidad": 1.0, "volumen": 1.0, "fundido_in": 0.0,
                "fundido_out": 0.0, "kf": {},
            }],
        }
        plan = rp.planificar(edicion, solo_audio=True)
        tmp = os.path.join(os.path.dirname(__file__), "_tmp_seek_audio_regresion")
        os.makedirs(tmp, exist_ok=True)
        try:
            wav = os.path.join(tmp, "audio.wav")
            cmd = ["ffmpeg", "-y", "-v", "error", *plan["entradas"],
                   "-filter_complex", plan["filtro"], "-map", plan["mapas"][0],
                   "-c:a", "pcm_s16le", wav]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            self.assertEqual(r.returncode, 0, r.stderr)
            medido = subprocess.run(
                ["ffmpeg", "-v", "info", "-nostats", "-i", wav, "-af", "volumedetect", "-f", "null", "NUL"],
                capture_output=True, text=True, timeout=90,
            )
            self.assertIn("max_volume:", medido.stderr)
            import re
            m = re.search(r"max_volume:\s*(-?[0-9.]+)\s*dB", medido.stderr)
            self.assertIsNotNone(m, medido.stderr)
            self.assertGreater(float(m.group(1)), -50.0)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
