# Changelog

## 1.0.0

- Primera version de escritorio ONEDIR para Windows.
- Agrega reproduccion de clips en Editar y Validar usando el reproductor del sistema.
- Agrega instalador de usuario para Windows y automatizacion de paquetes AppImage para Linux y DMG para macOS.
- Guarda los datos del usuario en las ubicaciones estandar de cada sistema.
- Usa codificacion H.264 por CPU en macOS y reintenta con libx264 si NVENC no esta disponible.
- Conserva modelos de Whisper, configuracion y resultados fuera de la distribucion.

## Desarrollo

El codigo fuente se ejecuta desde `scripts/`. Las dependencias del producto estan en `scripts/requirements.txt`; PyInstaller y sus archivos de trabajo viven en `scripts/build/`.