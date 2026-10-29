@echo off
setlocal
cd /d "%~dp0"
python -c "import webview, flask" 2>nul
if errorlevel 1 (
  echo Faltan dependencias. Ejecuta primero:
  echo   python -m pip install -r requirements.txt
  pause
  exit /b 1
)
python configuracion_app.py
endlocal
