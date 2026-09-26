@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Chua co moi truong Python. Xem INSTALL.md de cai dat lan dau.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" app.py
pause
