@echo off
REM ---- GRIB2 -> JMV local converter -------------------------------
cd /d "%~dp0"
where python >nul 2>nul || (echo Python not found on PATH & pause & exit /b 1)
echo Installing dependencies (first run only)...
python -m pip install -r requirements.txt --quiet
echo Starting server at http://127.0.0.1:5000
start "" http://127.0.0.1:5000
python app.py
pause
