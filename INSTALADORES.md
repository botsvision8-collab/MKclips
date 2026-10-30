# Instaladores de MKClips

- Windows x64: descarga `MKClips-Setup-win64.exe` desde [Releases](https://github.com/botsvision8-collab/MKclips/releases/latest). El setup instala la aplicación y, durante la instalación, configura WebView2 Runtime y descarga FFmpeg 9.0.2. Necesita conexión a Internet; no hace falta instalar Python ni FFmpeg por separado.
- Linux x86_64: descarga el AppImage desde Releases. Requiere FFmpeg en `PATH`, GTK 3 y WebKit2GTK 4.1.
- macOS Apple Silicon: descarga el DMG desde Releases y arrastra `MKClips.app` a Aplicaciones. Requiere FFmpeg en `PATH`; WebKit viene con macOS.

Los modelos de Whisper se descargan automáticamente la primera vez que se usan y se guardan con los datos de la aplicación. Las claves para proveedores externos de IA son opcionales.

El instalador de Windows obtiene WebView2 desde el bootstrapper oficial de Microsoft y FFmpeg Essentials desde Gyan.dev. La descarga de FFmpeg se verifica con SHA-256. Consulta [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) para los avisos y licencias.

PyInstaller debe ejecutarse en el mismo sistema operativo para el que se genera el paquete. Ejecuta **Build desktop installers** desde GitHub Actions o publica una etiqueta `v*`. Al publicar una etiqueta, GitHub Actions compila los tres paquetes y los publica en Releases.

La instalación y desinstalación conservan preferencias, resultados, registros, caché y modelos en la carpeta de datos del usuario.
