@echo off
setlocal
cd /d "%~dp0"
python -c "import PyInstaller, webview, flask" 2>nul
if errorlevel 1 (
  echo Faltan dependencias. Ejecuta primero:
  echo   python -m pip install -r requirements.txt
  exit /b 1
)
python -m PyInstaller --noconfirm --clean MKClips.spec
if errorlevel 1 exit /b %errorlevel%
echo.
echo Aplicacion lista: %~dp0dist\MKClips\MKClips.exe
endlocal
