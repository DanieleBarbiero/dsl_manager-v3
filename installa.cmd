@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
py -3.12 -m venv .venv
if not errorlevel 1 goto install
python -c "import sys; assert sys.version_info[:2] == (3,12)"
if errorlevel 1 goto missing
python -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info[:2] == (3,12)"
if errorlevel 1 goto missing
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install .
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
echo Installazione completata. Eseguire avvia.cmd.
pause
exit /b 0
:missing
echo Serve Python 3.12 a 64 bit, disponibile tramite py -3.12 o python.
pause
exit /b 2
:failed
echo Installazione non completata. Leggere l'errore precedente e ripetere.
pause
exit /b 1
