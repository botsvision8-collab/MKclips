@echo off
rem Diagnostico de un render que falla. Uso: arrastra el clip (el .mkv/.mp4 que abres con Editar) encima de este archivo.
if "%~1"=="" (
  echo Arrastra el clip original encima de este archivo, o escribe: diagnosticar_edicion.bat "ruta\del\clip.mkv"
  pause
  exit /b 1
)
cd /d "%~dp0scripts"
python diagnosticar_edicion.py "%~1"
echo.
echo Listo. El resultado tambien quedo en diagnostico_edicion.txt junto al clip.
pause
