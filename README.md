# MKClips

MKClips transcribe grabaciones de streams, identifica momentos y crea clips que puedes validar y editar.

## Instalar

- Windows x64: descarga `MKClips-Setup-win64.exe` desde [Releases](https://github.com/botsvision8-collab/MKclips/releases/latest).
- Linux x86_64: AppImage producido por el workflow de GitHub Actions.
- macOS Apple Silicon: DMG producido por el workflow de GitHub Actions.

Consulta [INSTALADORES.md](INSTALADORES.md) para los requisitos y cómo generar los paquetes de Linux/macOS. PyInstaller debe ejecutarse en el sistema operativo de destino.

En Windows, el instalador configura WebView2 Runtime y descarga FFmpeg automáticamente; necesita conexión a Internet durante la instalación. En Linux y macOS, instala FFmpeg y ponlo en `PATH`; Linux también requiere GTK 3 y WebKit2GTK 4.1. macOS usa WebKit del sistema. Los modelos de Whisper se descargan automáticamente al primer uso. Las claves de proveedores de IA son opcionales y no se incluyen en los paquetes.

Las preferencias, resultados, registros, caché y modelos quedan en la carpeta de datos del usuario: `%APPDATA%\MKClips` en Windows, `~/.local/share/MKClips` en Linux y `~/Library/Application Support/MKClips` en macOS. Desinstalar MKClips conserva esos datos.

## Ejecutar desde el código

Con Python 3.10 o posterior y FFmpeg instalados:

```powershell
python -m pip install -r scripts/requirements.txt
python scripts/mkclips_app.py
```

La clave del proveedor se define en el entorno antes de iniciar la app, por ejemplo `OLLAMA_API_KEY`.

## Construir

En Windows ejecuta `./scripts/build/empaquetar.ps1`. Para compilar los paquetes de los tres sistemas, ejecuta **Build desktop installers** desde GitHub Actions o publica una etiqueta `v*`. Al publicar una etiqueta, GitHub Actions añade los instaladores a Releases. Las compilaciones de Linux/macOS se ejecutan en runners nativos.

No incluyas `scripts/config.py`, claves, grabaciones, clips, resultados ni transcripciones al compartir el código. Consulta [SEGURIDAD.md](SEGURIDAD.md).

## Licencia

El codigo fuente de MKClips se publica bajo la licencia [MIT](LICENSE), que permite usarlo, modificarlo y redistribuirlo, conservando los avisos de copyright y licencia. Las fuentes tipograficas incluidas tienen sus propias licencias SIL Open Font License en `scripts/ui_web/fuentes/`. Las marcas y logotipos de plataformas en `assets/` pertenecen a sus respectivos titulares; la licencia MIT no concede derechos de marca.

Los componentes externos de los instaladores se detallan en [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
