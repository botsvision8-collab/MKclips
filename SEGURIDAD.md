# Seguridad y privacidad

- No guardes API keys ni contraseñas en `config.py`, código, capturas o archivos de configuración. `config.py` es local e ignorado por Git; `config_ejemplo.py` solo contiene valores genéricos.
- Para usar una clave, defínela en la variable de entorno que elegiste en Configuración (por ejemplo `OLLAMA_API_KEY` o `ASSEMBLYAI_API_KEY`). MKClips la usa durante la sesión y no la escribe en disco. En PowerShell, `$env:OLLAMA_API_KEY = "<tu-clave>"` dura en esa ventana; vuelve a abrir MKClips desde ella. Para definirla en el perfil de Windows, usa `setx OLLAMA_API_KEY "<tu-clave>"` y reinicia la sesión de Windows.
- La contraseña del WebSocket de OBS se acepta solo en la variable `OBS_WS_CONTRASENA` o en el campo de configuración durante la sesión; nunca se guarda en `config.py`.
- Los datos procesados, transcripciones, clips, criterios y registros son locales. Revísalos antes de compartirlos y mantenlos fuera de Git; `.gitignore` los excluye.
- La configuración de IA puede enviar prompts y contexto al proveedor seleccionado. AssemblyAI recibe audio cuando se elige ese motor. Revisa las condiciones del proveedor antes de habilitarlos.
- Al publicar, inspecciona tanto el código como el ZIP de distribución. Si una clave llegó a Git, revócala y crea un repositorio limpio sin ese historial.

## Contenido del paquete ONEDIR

El spec incluye `MKClips.exe`; módulos `scripts/**/*.py` salvo `config.py`, pruebas, bytecode y `scripts/pruebas_controladas`; recursos de `scripts/ui_web/` y `scripts/editor_web/`; carpetas `static/` y `plantillas/` en la raíz si existen; `assets/`; `VERSION`; y dependencias de ejecución de `scripts/requirements.txt`, PyWebView/EdgeChromium/pythonnet y sus bibliotecas nativas. No incluye `scripts/config.py`, archivos `config.local`, `.env`, claves, `scripts/resultados/`, `scripts/clips/`, `scripts/streams/`, transcripciones, criterios del creador, registros, cachés, modelos ni el contenido de `build/` o `dist/`.
