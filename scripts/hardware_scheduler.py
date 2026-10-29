"""Control ligero de recursos compartidos de MKClips.

# NOTE: LOCK_FILE is now an absolute path based on this file's location.
# A configurable timeout (default 30 s) avoids indefinite blocking when the GPU
# slot is already held by another process. The timeout can be overridden with the
# environment variable MKCLIPS_GPU_LOCK_TIMEOUT (seconds). When the timeout expires
# a RuntimeError is raised, which can be caught by the caller to recover gracefully.
"""

import contextlib
import os
import time

try:
    from .rutas_app import datos_dir
except ImportError:
    from rutas_app import datos_dir
LOCK_FILE = os.path.join(str(datos_dir()), ".mkclips_gpu.lock")
# Timeout (seconds) for acquiring the GPU lock. Can be overridden
# with the MKCLIPS_GPU_LOCK_TIMEOUT environment variable.
LOCK_TIMEOUT = float(os.getenv("MKCLIPS_GPU_LOCK_TIMEOUT", "30"))
RETRY_SECONDS = 1.0

@contextlib.contextmanager
def gpu_slot(nombre="GPU"):
    """Reserva el slot de GPU hasta que termina el bloque.

    En Windows usa un bloqueo real de archivo; al cerrar el proceso Windows
    libera el lock incluso si el proceso termina inesperadamente.
    """
    if os.name != "nt":
        yield
        return

    import msvcrt

    os.makedirs(os.path.dirname(os.path.abspath(LOCK_FILE)), exist_ok=True)
    with open(LOCK_FILE, "a+b") as f:
        f.seek(0)
        if not os.path.getsize(LOCK_FILE):
            f.write(b"0")
            f.flush()
        f.seek(0)

        adquirido = False
        start_time = time.time()
        while not adquirido:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                adquirido = True
            except OSError:
                elapsed = time.time() - start_time
                if elapsed > LOCK_TIMEOUT:
                    raise RuntimeError(f"GPU lock timeout after {LOCK_TIMEOUT} seconds for {nombre}.")
                print(f"GPU ocupada; esperando turno para {nombre}...")
                time.sleep(RETRY_SECONDS)

        try:
            print(f"GPU reservada para {nombre}.")
            yield
        finally:
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
