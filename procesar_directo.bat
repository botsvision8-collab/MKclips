@echo off
cd /d "%~dp0scripts"

echo ===============================
echo  PASO 1/5: Transcribiendo video
echo ===============================
python transcribir.py
if errorlevel 1 (
    echo.
    echo ERROR en transcribir.py, se detiene el proceso.
    pause
    exit /b 1
)

echo.
echo ===============================
echo  PASO 2/5: Detectando reacciones fuertes en el audio
echo ===============================
python detectar_eventos_audio.py
if errorlevel 1 (
    echo.
    echo ERROR en detectar_eventos_audio.py, se detiene el proceso.
    pause
    exit /b 1
)

echo.
echo ===============================
echo  PASO 3/5: Identificando clips
echo ===============================
python identificar_clips.py
if errorlevel 1 (
    echo.
    echo ERROR en identificar_clips.py, se detiene el proceso.
    pause
    exit /b 1
)

echo.
echo ===============================
echo  PASO 4/5: Cortando clips con NVENC
echo ===============================
python cortar_clips_nvenc.py
if errorlevel 1 (
    echo.
    echo ERROR en cortar_clips_nvenc.py, se detiene el proceso.
    pause
    exit /b 1
)

echo.
echo ===============================
echo  PASO 5/5: Verificando segmentos
echo ===============================
python verificar_segmentos.py
if errorlevel 1 (
    echo.
    echo ERROR en verificar_segmentos.py, se detiene el proceso.
    pause
    exit /b 1
)

echo.
echo ===============================
echo  TODO LISTO. Revisa la carpeta Clips.
echo ===============================
pause
