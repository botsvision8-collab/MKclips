# Avisos de componentes de terceros

## FFmpeg para Windows

Durante la instalación de Windows, MKClips descarga FFmpeg 9.0.2 Essentials para Windows x64 directamente desde Gyan.dev. El archivo se verifica antes de extraerlo. FFmpeg se instala como un ejecutable separado en `bin` y no forma parte del código MKClips bajo MIT.

La compilación Essentials está licenciada bajo GPLv3 e incluye libx264. El instalador deja en la carpeta de la aplicación un aviso con la licencia, versión, checksum y enlaces a la compilación y al código fuente correspondiente.

- Paquete y datos de compilación: <https://www.gyan.dev/ffmpeg/builds/>
- Código fuente de FFmpeg 9.0.2: <https://github.com/FFmpeg/FFmpeg/commit/946fcce07b>
- Licencia e información legal de FFmpeg: <https://ffmpeg.org/legal.html>
- Texto completo de GPLv3 incluido en `third_party/licenses/GPL-3.0.txt`.
- SHA-256 del paquete `ffmpeg-9.0.2-essentials_build.zip`: `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba`

## WebView2 Runtime

El instalador de Windows incluye el bootstrapper de Microsoft y lo ejecuta durante la instalación. Si el runtime no está instalado, el bootstrapper lo descarga desde Microsoft. WebView2 Runtime se distribuye bajo los términos de Microsoft.

- Información de distribución de Microsoft: <https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution>

## Fuentes tipográficas

Las tipografías Montserrat y JetBrains Mono incluidas en el código conservan sus licencias SIL Open Font License 1.1, copiadas junto a los archivos de fuentes en `scripts/ui_web/fuentes/`.
