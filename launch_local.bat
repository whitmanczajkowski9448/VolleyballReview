@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Run setup_local.bat first. & pause & exit /b 1)
if not exist ".streamlit\secrets.toml" echo # Local settings> ".streamlit\secrets.toml"
".venv\Scripts\python.exe" migrate_local.py --backup || (echo Backup failed; launch canceled. & pause & exit /b 1)
".venv\Scripts\python.exe" -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
pause
