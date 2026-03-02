@echo off
REM Ollama Deployment Script for PLM (Windows)
REM This script deploys your trained model to Ollama for offline use

echo ==========================================
echo PLM Ollama Deployment Script (Windows)
echo ==========================================
echo.

REM Configuration
set MODEL_DIR=.\models\my-private-model-v1
set MODEL_NAME=my-private-ai
set MODELFILE=.\Modelfile

REM Check if Ollama is installed
echo Checking Ollama installation...
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Ollama is not installed!
    echo.
    echo Please install Ollama first:
    echo   Download from: https://ollama.ai/download
    echo.
    pause
    exit /b 1
)

echo OK: Ollama is installed
echo.

REM Check if model directory exists
echo Checking model directory...
if not exist "%MODEL_DIR%" (
    echo ERROR: Model directory not found: %MODEL_DIR%
    echo.
    echo Please ensure you have:
    echo   1. Trained your model using the Colab notebook
    echo   2. Downloaded the model folder
    echo   3. Placed it in: %MODEL_DIR%
    echo.
    pause
    exit /b 1
)

echo OK: Model directory found
echo.

REM Check if Modelfile exists
echo Checking Modelfile...
if not exist "%MODELFILE%" (
    echo ERROR: Modelfile not found!
    pause
    exit /b 1
)

echo OK: Modelfile found
echo.

REM Create Ollama model
echo Creating Ollama model: %MODEL_NAME%
echo This may take a few minutes...
echo.

ollama create %MODEL_NAME% -f %MODELFILE%

if %errorlevel% equ 0 (
    echo.
    echo ==========================================
    echo SUCCESS: Deployment successful!
    echo ==========================================
    echo.
    echo Your model is ready to use!
    echo.
    echo To use your model:
    echo   ollama run %MODEL_NAME%
    echo.
    echo To use in Python:
    echo   import ollama
    echo   response = ollama.chat^(model='%MODEL_NAME%', messages=[...]^)
    echo.
    echo To use via API:
    echo   curl http://localhost:11434/api/chat -d "{\"model\": \"%MODEL_NAME%\", \"messages\": [...]}"
    echo.
) else (
    echo.
    echo ERROR: Deployment failed!
    echo Please check the error messages above.
    echo.
)

pause
