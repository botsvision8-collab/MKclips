# -*- coding: utf-8 -*-
"""Diagnostico del selector: cuantos momentos propone la IA y por que se pierden.

Solo observa y escribe un archivo (``selector_diagnostico.json``); nunca cambia que
clips salen. Si algo falla al guardar, el pipeline continua.
"""
from __future__ import annotations

import json
import os
import threading


def _resumen(c):
    segs = c.get("segmentos")
    if isinstance(segs, list) and len(segs) > 1:
        dur = sum(max(0.0, float(s["fin"]) - float(s["inicio"])) for s in segs)
    else:
        dur = max(0.0, float(c.get("fin", 0)) - float(c.get("inicio", 0)))
    return {"titulo": str(c.get("titulo") or c.get("razon") or "")[:80], "tipo": c.get("tipo"),
            "inicio": round(float(c.get("inicio", 0)), 1), "fin": round(float(c.get("fin", 0)), 1),
            "duracion": round(dur, 1)}


class Diagnostico:
    def __init__(self):
        self.propuestos = 0
        self.eventos = []
        self._lock = threading.Lock()

    def propuesto(self, cantidad):
        with self._lock:
            self.propuestos += int(cantidad)

    def perdido(self, candidato, etapa, motivo):
        try:
            registro = {"etapa": etapa, "motivo": motivo, **_resumen(candidato)}
        except (KeyError, TypeError, ValueError):
            return
        with self._lock:
            self.eventos.append(registro)

    def perdidos_entre(self, antes, despues, etapa, motivo):
        """Registra los de ``antes`` que ya no estan en ``despues`` (comparacion por identidad)."""
        quedan = {id(c) for c in despues}
        for c in antes:
            if id(c) not in quedan:
                self.perdido(c, etapa, motivo)

    def resumen(self):
        por_motivo = {}
        for e in self.eventos:
            clave = f"{e['etapa']}: {e['motivo']}"
            por_motivo[clave] = por_motivo.get(clave, 0) + 1
        return {"propuestos_por_la_ia": self.propuestos, "perdidos": len(self.eventos), "por_motivo": por_motivo}

    def guardar(self, ruta, extra=None):
        try:
            datos = {"resumen": self.resumen(), "perdidos": self.eventos}
            if extra:
                datos["resumen"].update(extra)
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=2)
            return True
        except (OSError, TypeError, ValueError):
            return False

    def imprimir(self):
        r = self.resumen()
        print(f"[diagnostico] La IA propuso {r['propuestos_por_la_ia']} momentos; se perdieron {r['perdidos']}.")
        for clave, n in sorted(r["por_motivo"].items(), key=lambda kv: -kv[1]):
            print(f"[diagnostico]   {n} x {clave}")
