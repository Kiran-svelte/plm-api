#!/bin/bash

# Quick Deploy Script for PLM SaaS

echo "========================================"
echo "PLM SaaS - Quick Deploy"
echo "========================================"
echo ""

# Check if in correct directory
if [ ! -f "api.py" ]; then
    echo "Error: Run this from the saas/ directory"
    exit 1
fi

echo "Step 1: Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "Step 2: Testing API locally..."
python -c "from api import app; print('✓ API imports successfully')"

echo ""
echo "Step 3: Starting local server..."
echo ""
echo "API will be available at: http://localhost:8000"
echo "Dashboard will be at: http://localhost:8000/dashboard.html"
echo "API docs at: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"
echo ""

uvicorn api:app --host 0.0.0.0 --port 8000 --reload
