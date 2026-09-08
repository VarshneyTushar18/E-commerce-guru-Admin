@echo off
cd /d "%~dp0"
call venv\Scripts\activate
echo Starting Ecomm Guru Admin on http://localhost:8765
uvicorn app.main:app --host 0.0.0.0 --port 8765
