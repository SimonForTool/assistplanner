@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python neni nainstalovany. Stahnete ho z https://www.python.org/downloads/
  echo a pri instalaci zaskrtnete "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist .venv (
  echo Prvni spusteni: instaluji knihovny, chvili to potrva...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo Instalace knihoven selhala.
  pause
  exit /b 1
)

if not exist .env copy .env.example .env >nul

echo.
echo Aplikace startuje na http://localhost:5000
echo Toto okno nechte otevrene, zavrenim se aplikace vypne.
echo.
start "" http://localhost:5000
python app.py
pause
