# MKClips como aplicación de escritorio

La interfaz se abre en una ventana propia con Microsoft Edge WebView2, sin pestañas ni barra de dirección del navegador. Workflow, Validar clips, Editar y Configuración siguen usando el mismo servidor local y las mismas funciones del proyecto.

## Ejecutar desde el código

```bat
cd scripts
python -m pip install -r requirements.txt
iniciar_mkclips.bat
```

Windows debe tener instalado Microsoft Edge WebView2 Runtime.

## Crear el ejecutable

```bat
cd scripts
python -m pip install -r requirements.txt
crear_mkclips_exe.bat
```

El ejecutable y sus recursos quedan en `scripts/dist/MKClips/`. Se distribuye la carpeta completa para mantener juntos los módulos Python, recursos web y dependencias nativas; se inicia desde `MKClips.exe`.

El ejecutable también puede iniciar el servidor local como proceso auxiliar con `MKClips.exe --server`; la ventana de escritorio lo usa para servir las pantallas y las rutas actuales.
