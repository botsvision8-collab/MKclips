# Instaladores de MKClips 1.0.0

- Windows x64: `dist/MKClips-Setup-win64.exe` instala MKClips para el usuario actual y crea accesos directos en Inicio. `dist/MKClips-v1.0.0-win64.zip` es el paquete portable.
- Linux x86_64: el workflow de GitHub Actions genera `MKClips-1.0.0-x86_64.AppImage` en un runner Ubuntu con GTK y WebKit2GTK.
- macOS Apple Silicon: el workflow genera un DMG que permite arrastrar `MKClips.app` a Aplicaciones.

PyInstaller debe ejecutarse en el mismo sistema operativo para el que se genera el paquete. Ejecuta `Build desktop installers` desde la pestaña Actions o publica una etiqueta `v*` para generar los artefactos de Linux y macOS. Este equipo Windows solo puede construir el ejecutable y el instalador de Windows.

FFmpeg debe estar instalado y disponible en `PATH`. Windows también necesita Microsoft Edge WebView2 Runtime. Linux necesita GTK 3 y WebKit2GTK 4.1. macOS usa WebKit del sistema. La instalación y desinstalación conservan preferencias, resultados, registros, caché y modelos en la carpeta de datos del usuario.
