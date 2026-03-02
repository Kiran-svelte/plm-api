#!/bin/bash

# Ollama Deployment Script for PLM
# This script deploys your trained model to Ollama for offline use

set -e

echo "=========================================="
echo "PLM Ollama Deployment Script"
echo "=========================================="
echo ""

# Configuration
MODEL_DIR="./models/my-private-model-v1"
MODEL_NAME="my-private-ai"
MODELFILE="./Modelfile"

# Check if Ollama is installed
echo "Checking Ollama installation..."
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama is not installed!"
    echo ""
    echo "Please install Ollama first:"
    echo "  Windows: https://ollama.ai/download"
    echo "  Linux: curl -fsSL https://ollama.ai/install.sh | sh"
    echo "  macOS: brew install ollama"
    exit 1
fi

echo "✅ Ollama is installed"
echo ""

# Check if model directory exists
echo "Checking model directory..."
if [ ! -d "$MODEL_DIR" ]; then
    echo "❌ Model directory not found: $MODEL_DIR"
    echo ""
    echo "Please ensure you have:"
    echo "  1. Trained your model using the Colab notebook"
    echo "  2. Downloaded the model folder"
    echo "  3. Placed it in: $MODEL_DIR"
    exit 1
fi

echo "✅ Model directory found"
echo ""

# Check if Modelfile exists
echo "Checking Modelfile..."
if [ ! -f "$MODELFILE" ]; then
    echo "❌ Modelfile not found!"
    exit 1
fi

echo "✅ Modelfile found"
echo ""

# Create Ollama model
echo "Creating Ollama model: $MODEL_NAME"
echo "This may take a few minutes..."
echo ""

ollama create "$MODEL_NAME" -f "$MODELFILE"

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ Deployment successful!"
    echo "=========================================="
    echo ""
    echo "Your model is ready to use!"
    echo ""
    echo "To use your model:"
    echo "  ollama run $MODEL_NAME"
    echo ""
    echo "To use in Python:"
    echo "  import ollama"
    echo "  response = ollama.chat(model='$MODEL_NAME', messages=[...])"
    echo ""
    echo "To use via API:"
    echo "  curl http://localhost:11434/api/chat -d '{\"model\": \"$MODEL_NAME\", \"messages\": [...]}'"
    echo ""
else
    echo ""
    echo "❌ Deployment failed!"
    echo "Please check the error messages above."
    exit 1
fi
