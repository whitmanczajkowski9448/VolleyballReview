@echo off
cd /d "%~dp0"
where py >nul 2>nul || (echo Install Python 3.11 or newer from python.org first. & pause & exit /b 1)
py -3 -m venv .venv || (pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install --upgrade pip || (pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)
if not exist data mkdir data
if not exist ".streamlit\secrets.toml" (
  echo # Local settings; add DVSPORT_COOKIE if needed.> ".streamlit\secrets.toml"
)
echo Setup complete. Import your old data before launching if possible.
pause
