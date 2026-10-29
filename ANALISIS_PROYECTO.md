# Analisis tecnico de MKClips

## Inventario y dependencias

### Pipeline principal

```text
procesar_directo.bat
  -> transcribir.py
       -> faster-whisper / ctranslate2
       -> ultimo_video.txt
       -> transcripcion.json
  -> detectar_eventos_audio.py
       -> ffmpeg -> audio_temp.wav
       -> librosa/numpy
       -> eventos_audio.json
  -> identificar_clips.py
       -> transcripcion.json + eventos_audio.json
       -> ejemplos_buenos.json + resultados_reales.json (opcionales)
       -> Ollama Cloud
       -> candidatos_todos.json, candidatos_cortos.json,
          clips_sugeridos.json, resumen_plan.json (opcional)
  -> cortar_clips_nvenc.py
       -> ultimo_video.txt + transcripcion.json + clips_sugeridos.json
       -> ffprobe
       -> ffmpeg/NVENC
       -> historial_clips.json + clips MKV
```

`procesar_multiples.py` es el motor de orquestacion: lanza cada etapa como subproceso, registra `estado_progreso.json`, `historial_tiempos_proceso.json` y `logs/pipeline.log`, permite reanudar y lo usa tambien `control_grabacion.py`, `procesar_cola_bg.py`, `reanudar_ultimo_proceso.py`, `transcribir.py` y `configuracion_app.py`.

### Modulos de soporte

- `config.py`: configuracion real local, rutas, Whisper, NVENC, Ollama, cache y metricas.
- `config_ejemplo.py`: plantilla reducida de configuracion.
- `configuracion_app.py`: GUI Tkinter; genera/lee `config.py`, descarga videos y lanza colas.
- `control_grabacion.py`: OBS WebSocket, deteccion de archivos nuevos y disparo del pipeline.
- `panel_grabacion.py`: servidor Flask embebido para el panel de OBS.
- `OBS/obs_disparar_pipeline.py`: inicia el panel al cargar OBS; no lanza el pipeline por segunda vez.
- `descargar_video.py`: descarga con yt-dlp.
- `notificacion_progreso.py`: UI de progreso independiente.
- `agregar_ejemplo.py` y `registrar_resultado.py`: aprendizaje/calibracion manual.
- `revisar.py`: inspeccion rapida de la transcripcion.
- `herramientas_busqueda/buscar_por_sonido.py`: correlacion de audio de una referencia.
- `herramientas_busqueda/buscar_por_imagen.py`: coincidencia de plantilla visual.
- `buscar_multiples_referencias.py` y `herramientas_busqueda/buscar_multiples_referencias.py`: busqueda combinada de sonido/imagen y cortes opcionales.

## Imports y contratos

- Dependencias externas: `faster-whisper`, `ollama`, `librosa`, `soundfile`, `scipy`, `numpy`, `opencv-python-headless`; el codigo usa tambien opcionalmente `yt-dlp`, `flask`, `obsws-python`, `pystray/Pillow` y `ctranslate2`.
- Dependencias internas directas: `transcribir -> procesar_multiples`; `control_grabacion -> procesar_multiples`; `configuracion_app -> procesar_multiples, descargar_video, buscar_multiples_referencias`; `panel_grabacion -> control_grabacion`; `OBS -> panel_grabacion` por subproceso.
- Los scripts del pipeline se comunican principalmente por archivos en el directorio de trabajo, no por imports ni argumentos.

## JSON leidos y escritos

- `ultimo_video.txt`: ruta absoluta y nombre base elegidos por transcripcion; lo leen eventos, identificacion y corte.
- `transcripcion.json`: lista de `{inicio, fin, texto}`.
- `eventos_audio.json`: lista de `{inicio, fin}`.
- `candidatos_todos.json` y `candidatos_cortos.json`: candidatos de identificacion.
- `clips_sugeridos.json`: lista final con `tipo`, `inicio`, `fin`, `titulo`, `razon`.
- `resumen_plan.json`: objeto con `titulo` y lista `momentos`.
- `historial_clips.json`, `resultados_reales.json`, `ejemplos_buenos.json`: historial y calibracion.
- `estado_progreso.json`, `historial_tiempos_proceso.json`: estado, ETA y metricas del orquestador.
- `resultados_busqueda_sonido.json`, `resultados_busqueda_imagen.json`, `resultados_multiples_referencias.json`: resultados de herramientas de busqueda.
- `config.py` se genera como Python, no como JSON.

No se cambia ninguno de estos formatos.

## Duplicacion y trabajo repetido

1. `buscar_multiples_referencias.py` y su copia bajo `herramientas_busqueda/` son duplicados.
2. La busqueda visual multiple ya compara todas las plantillas en un recorrido, pero reposiciona `VideoCapture` en cada frame; esto fuerza busquedas repetidas del contenedor.
3. La generacion del resumen ejecuta FFmpeg una vez por momento y otra vez para concatenar. Es el mayor grupo de llamadas repetidas en el corte.
4. El pipeline extrae audio para Whisper en la rama CPU por trozos y `detectar_eventos_audio.py` vuelve a extraer el video completo. La reutilizacion de audio es posible, pero requiere un cache por video para no mezclar streams porque los nombres de salida actuales son globales.
5. La validacion de salidas del orquestador busca nombres por video (`{base}...`), mientras las etapas actuales escriben nombres globales (`transcripcion.json`, `eventos_audio.json`, `clips_sugeridos.json`); por ello el salto por archivo no es fiable y el estado es la unica fuente segura actual.
6. `ffprobe` de duracion aparece en transcripcion y orquestador, pero corren en procesos separados; dentro de cada proceso no hay cache compartida.

## Cuellos de botella

- Whisper `large-v3` domina el tiempo de CPU/GPU.
- La extraccion de audio completa para eventos lee y convierte todo el stream.
- Ollama procesa bloques solapados y despues hace ranking/refinamiento; ya existe compactacion y batching parcial.
- NVENC acelera clips individuales, pero el resumen tenia N+1 codificaciones.
- La correlacion de sonido usa convolucion sobre arrays completos; es correcta pero consume RAM/CPU para streams muy largos.
- La coincidencia visual con `cap.set` por muestra puede ser mucho mas lenta que una lectura secuencial.

## Oportunidades aplicadas en Fase 2

- Convertir el modulo duplicado de busqueda multiple en un facade compatible.
- Leer frames secuencialmente en las dos rutas de busqueda visual multiple.
- Generar el resumen mediante un unico `filter_complex` de trim/concat y una codificacion NVENC.

Estas mejoras mantienen APIs, nombres de archivos y formatos JSON. El cache de audio y un cache de etapas por video quedan identificados como siguiente ampliacion: deben incorporar una clave de archivo (ruta, mtime y tamano) antes de activarse para evitar reutilizar resultados de otro stream.
