@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ejecutar instalar.bat primero.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -u server.py
if errorlevel 1 pause
