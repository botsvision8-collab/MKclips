"""
Copia este archivo como "config.py" (mismo carpeta) y ajusta los valores a
tu propia configuracion. "config.py" esta en .gitignore, nunca se sube a
GitHub - asi cada quien mantiene sus rutas y datos personales en privado.
"""

# --- Rutas de carpetas (ajusta a las tuyas) ---
CARPETA_STREAMS = r"%USERPROFILE%\Documents\MKClips\streams"
CARPETA_CLIPS_BASE = r"%USERPROFILE%\Documents\MKClips\clips"
CARPETA_RESULTADOS = ""  # Vacia = scripts/resultados
# Reservada para una futura integración; actualmente no tiene consumidor.

# --- Contexto al terminar una grabacion desde OBS ---
MOSTRAR_CONTEXTO_POST_STREAM = True
OBS_MODO_GRABACION_DEFAULT = "horizontal"
OBS_SOLO_GRABAR_DEFAULT = False
OBS_BORRAR_ORIGINAL_AL_TERMINAR = False

# --- Conexion OBS WebSocket ---
OBS_WS_HOST = "localhost"
OBS_WS_PUERTO = 4455
OBS_WS_CONTRASENA = ""

# 0 significa sin límite. Se aplican al identificar clips completos.
DURACION_MIN_CLIP = 0
DURACION_MAX_CLIP = 0

# --- Contexto para mejorar la transcripcion ---
# Opcional: agrega aquí vocabulario genérico del juego o tema que grabas.
CONTEXTO_TRANSCRIPCION = (
    "Este es un directo de gaming en español. "
    "Añade únicamente términos generales que ayuden a reconocer el vocabulario."
)
