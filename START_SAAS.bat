@echo off
REM PLM SaaS - Quick Start Script

echo ============================================
echo PLM SAAS PLATFORM - QUICK START
echo ============================================
echo.

cd saas

echo Step 1: Installing dependencies...
pip install -q fastapi uvicorn pydantic requests python-dotenv pyyaml tenacity rich tqdm aiofiles

echo.
echo Step 2: Testing API...
python -c "from api import app; print('[OK] API ready')"

echo.
echo ============================================
echo STARTING PLM SAAS PLATFORM
echo ============================================
echo.
echo Admin Dashboard: http://localhost:8000/dashboard.html
echo API Docs: http://localhost:8000/docs
echo.
echo Press Ctrl+C to stop
echo.

uvicorn api:app --host 0.0.0.0 --port 8000 --reload
