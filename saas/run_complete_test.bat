@echo off
REM Start API server and run complete flow test

echo Starting API server...
cd D:\cmp\Plm\saas

start /B python -m uvicorn api:app --host 127.0.0.1 --port 8000

echo Waiting for server to start...
timeout /t 5 /nobreak > nul

echo Running complete flow test...
python test_complete_flow.py

echo.
echo Test complete! Press any key to stop server...
pause

taskkill /F /IM python.exe /FI "WINDOWTITLE eq uvicorn*"
