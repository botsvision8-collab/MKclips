"""
Cola de procesamiento de streams para MKClips.
Mantiene una lista ordenada de videos a procesar, persiste su estado en disco y
se encarga de lanzar el pipeline existente (procesar_multiples.procesar_un_video)
de forma secuencial, respetando el hardware_scheduler (GPU lock) y la caché.

Estados de cada stream:
    ESPERANDO   – todavía no iniciado
    PROCESANDO – en ejecución
    COMPLETADO – terminó sin errores
    ERROR       – falló alguna etapa
    CANCELADO   – la cola fue cancelada antes de iniciar este stream
    OMITIDO     – se omitió por alguna razón (no usado actualmente)

Persistencia en JSON bajo RESULTADOS_DIR/cola_procesamiento.json.
"""

import os
import json
import threading
import time
from typing import List, Dict, Callable

try:
    from . import procesar_multiples
except ImportError:
    import procesar_multiples

RESULT_FILE_NAME = "cola_procesamiento.json"

ESTADOS_PENDIENTES = ("ESPERANDO", "PROCESANDO")

class QueueManager:
    """Gestor de la cola de streams.

    Parameters
    ----------
    resultados_dir: str
        Directorio donde se guardará el archivo de estado.
    notificar: Callable[[str], None]
        Función para enviar mensajes al UI (ej. actualizar etiqueta).
    """

    def __init__(self, resultados_dir: str, notificar: Callable[[str], None] = print):
        self.resultados_dir = os.path.abspath(resultados_dir)
        os.makedirs(self.resultados_dir, exist_ok=True)
        self.notificar = notificar
        self._queue: List[Dict] = []  # cada elemento: {"path": str, "status": str}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._pause_event = threading.Event()
        self._cancel_event = threading.Event()
        self._load_state()

    # ---------------------------------------------------------------------
    # Persistencia
    # ---------------------------------------------------------------------
    def _state_file(self) -> str:
        return os.path.join(self.resultados_dir, RESULT_FILE_NAME)

    def _load_state(self) -> None:
        try:
            with open(self._state_file(), "r", encoding="utf-8") as f:
                data = json.load(f)
            self._queue = data.get("queue", [])
            # Normalizar campos
            for item in self._queue:
                if "status" not in item:
                    item["status"] = "ESPERANDO"
        except Exception:
            self._queue = []

    def _save_state(self) -> None:
        data = {
            "queue": self._queue,
            "timestamp": time.time(),
        }
        try:
            tmp = self._state_file() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._state_file())
        except Exception as e:
            self.notificar(f"[Cola] Error al guardar estado: {e}")

    # ---------------------------------------------------------------------
    # Operaciones de cola
    # ---------------------------------------------------------------------
    def get_queue(self) -> List[Dict]:
        """Devuelve una copia de la lista de items de la cola."""
        with self._lock:
            return [item.copy() for item in self._queue]

    def add_stream(self, path: str, contexto: str = "") -> None:
        """Añade un stream. ``contexto`` (opcional) es lo que el creador cuenta de ese
        video (juego, estilo...): llega a la IA que elige los clips."""
        if not os.path.isfile(path):
            self.notificar(f"[Cola] Archivo no encontrado: {path}")
            return
        with self._lock:
            self._queue.append({"path": os.path.abspath(path), "status": "ESPERANDO", "contexto": str(contexto or "").strip()})
            self._save_state()
        self.notificar(f"[Cola] Añadido stream: {os.path.basename(path)}")

    def set_contexto(self, path: str, contexto: str) -> bool:
        """Cambia el contexto de UN stream que aun no se procesa. Devuelve si lo encontro."""
        with self._lock:
            for item in self._queue:
                if item["path"] == path and item["status"] == "ESPERANDO":
                    item["contexto"] = str(contexto or "").strip()
                    self._save_state()
                    return True
        return False

    def aplicar_contexto_pendientes(self, contexto: str) -> int:
        """Pone el mismo contexto a todos los streams que siguen esperando. Devuelve cuantos."""
        with self._lock:
            n = 0
            for item in self._queue:
                if item["status"] == "ESPERANDO":
                    item["contexto"] = str(contexto or "").strip()
                    n += 1
            if n:
                self._save_state()
        return n

    def add_folder(self, folder: str, contexto: str = "") -> None:
        """Añade todos los archivos de vídeo dentro de *folder* y sus sub‑directorios.
        Soporta una amplia variedad de extensiones de vídeo comunes y notifica al usuario
        cuántos archivos se han añadido (o si no se encontró ninguno)."""
        if not os.path.isdir(folder):
            self.notificar(f"[Cola] Carpeta no encontrada: {folder}")
            return
        # Extensiones de vídeo reconocidas (case‑insensitive). Se pueden ampliar fácilmente.
        extens = (
            ".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm",
            ".mpeg", ".mpg", ".m4v", ".3gp", ".3g2",
        )
        added = 0
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(extens):
                    self.add_stream(os.path.join(root, f), contexto)
                    added += 1
        if added:
            self.notificar(f"[Cola] Añadidos {added} vídeo(s) desde la carpeta {os.path.basename(folder)}")
        else:
            self.notificar(f"[Cola] No se encontraron vídeos soportados en la carpeta {folder}")

    # ---------------------------------------------------------------------
    # Control de ejecución
    # ---------------------------------------------------------------------
    def start(self) -> None:
        """Inicia la ejecución de la cola si no está ya corriendo."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                self.notificar("[Cola] La cola ya está en ejecución.")
                return
            self._pause_event.clear()
            self._cancel_event.clear()
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()
            self.notificar("[Cola] Inicio de procesamiento.")

    def pause(self) -> None:
        self._pause_event.set()
        self.notificar("[Cola] Pausado.")

    def resume(self) -> None:
        if self._pause_event.is_set():
            self._pause_event.clear()
            self.notificar("[Cola] Reanudado.")

    def cancel(self) -> None:
        self._cancel_event.set()
        self.notificar("[Cola] Cancelado. Se esperará al final del stream actual.")

    def _worker(self) -> None:
        """Itera sobre la cola y procesa cada stream.
        Respeta pausa y cancelación. Actualiza el estado de cada ítem y persiste.
        La pausa y la cancelación surten efecto entre un stream y el siguiente.
        """
        hechos = 0
        try:
            while True:
                # Pausa
                if self._pause_event.is_set():
                    time.sleep(0.5)
                    continue
                # Cancelación pendiente
                if self._cancel_event.is_set():
                    with self._lock:
                        for item in self._queue:
                            if item["status"] in ("ESPERANDO", "PROCESANDO"):
                                item["status"] = "CANCELADO"
                        self._save_state()
                    break
                # Siguiente pendiente
                with self._lock:
                    pending = [i for i, it in enumerate(self._queue) if it["status"] == "ESPERANDO"]
                    if not pending:
                        break
                    item = self._queue[pending[0]]
                    item["status"] = "PROCESANDO"
                    self._save_state()
                    path = item["path"]
                    contexto = item.get("contexto", "")
                    total = hechos + len(pending)
                # La ventana de progreso muestra "Stream i/N" y no se cierra entre streams.
                procesar_multiples.establecer_info_cola(hechos + 1, total, activa=True)
                self.notificar(f"[Cola] Procesando {hechos + 1}/{total}: {os.path.basename(path)}")
                try:
                    ok = procesar_multiples.procesar_un_video(
                        path,
                        modo_automatico=True,
                        notificar=self.notificar,
                        contexto_stream=contexto,
                    )
                except Exception as e:
                    ok = False
                    self.notificar(f"[Cola] Excepción inesperada: {e}")
                hechos += 1
                with self._lock:
                    item["status"] = "COMPLETADO" if ok else "ERROR"
                    self._save_state()
        finally:
            procesar_multiples.finalizar_info_cola()
            self.notificar("[Cola] Procesamiento finalizado.")
            with self._lock:
                self._thread = None

    # ---------------------------------------------------------------------
    # Utilidades de inspección
    # ---------------------------------------------------------------------
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def pending_count(self) -> int:
        """Cantidad de streams que todavía faltan por procesar."""
        with self._lock:
            return sum(1 for item in self._queue if item["status"] in ESTADOS_PENDIENTES)

    def depurar_sesion_anterior(self) -> int:
        """Limpia la cola guardada de una sesión previa y devuelve cuántos
        streams siguen realmente pendientes.

        - Los streams ya procesados (COMPLETADO/OMITIDO/CANCELADO) se quitan.
        - Un stream que quedó PROCESANDO porque la app se cerró vuelve a ESPERANDO.
        - Los pendientes cuyo archivo ya no existe se descartan.
        Los ERROR se conservan para que el usuario los vea hasta limpiarlos.
        No toca nada si la cola está en ejecución.
        """
        if self.is_running():
            return self.pending_count()
        with self._lock:
            depurada = []
            for item in self._queue:
                estado = item.get("status", "ESPERANDO")
                if estado in ("COMPLETADO", "OMITIDO", "CANCELADO"):
                    continue
                if estado in ESTADOS_PENDIENTES:
                    if not os.path.isfile(item.get("path", "")):
                        continue
                    item["status"] = "ESPERANDO"
                depurada.append(item)
            cambio = len(depurada) != len(self._queue)
            self._queue = depurada
            if cambio:
                self._save_state()
            return sum(1 for item in self._queue if item["status"] in ESTADOS_PENDIENTES)

    def limpiar_terminados(self) -> None:
        """Quita de la lista todo lo que ya no está pendiente (incluye ERROR)."""
        with self._lock:
            self._queue = [i for i in self._queue if i["status"] in ESTADOS_PENDIENTES]
            self._save_state()

    def descartar_todo(self) -> None:
        """Vacía la cola (solo si no está en ejecución)."""
        if self.is_running():
            return
        with self._lock:
            self._queue = []
            self._save_state()
