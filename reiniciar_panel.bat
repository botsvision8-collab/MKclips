@echo off
rem Cierra el panel de MKClips que quedo abierto en segundo plano (el que sirve el editor y el render).
rem Despues pulsa "Editar" en la app: arranca uno nuevo con los archivos actualizados.
set ENCONTRADO=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5678" ^| findstr "LISTENING"') do (
  echo Cerrando el panel (proceso %%a)...
  taskkill /PID %%a /F
  set ENCONTRADO=1
)
if "%ENCONTRADO%"=="0" echo No habia ningun panel abierto.
echo.
echo Listo. Ahora abre el editor de nuevo desde la app (boton Editar).
pause
