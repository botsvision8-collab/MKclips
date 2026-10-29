@echo off
rem Inicia el panel de grabacion de OBS sin necesidad de OBS (util para comprobar que funciona).
rem Deja esta ventana abierta; el panel queda en http://localhost:5678
cd /d "%~dp0scripts"
python -c "import flask, obsws_python" 2>nul || (
  echo Faltan librerias. Instalando flask y obsws-python...
  python -m pip install flask obsws-python
)
python panel_grabacion.py
pause
