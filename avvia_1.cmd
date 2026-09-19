@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Eseguire prima installa.cmd.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m dslm3 --workspace "%~dp0workspace" serve %*
if errorlevel 1 pause
