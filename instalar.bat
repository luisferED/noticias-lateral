@echo off
setlocal
cd /d "%~dp0"
echo Se requiere Python 3.12 o superior de 64 bits.
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -m pip install -r requirements-ndi.txt
if errorlevel 1 goto error
if not exist .env copy .env.example .env >nul
echo Instalacion lista. Ejecutar iniciar.bat e iniciar_ndi.bat.
exit /b 0
:error
echo No se pudo completar la instalacion. Revisar el error anterior.
pause
exit /b 1
