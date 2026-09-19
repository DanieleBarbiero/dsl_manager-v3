@echo off
setlocal
cd /d "%~dp0"
set "VENV=C:\_Support\.venv_dslm3"
if not exist "%VENV%\Scripts\python.exe" (
  echo Eseguire prima installa.cmd.
  pause
  exit /b 1
)
"%VENV%\Scripts\python.exe" -m dslm3 --workspace "%~dp0workspace" serve %*
if errorlevel 1 pause
