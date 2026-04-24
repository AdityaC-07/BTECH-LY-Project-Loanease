#!/bin/bash

echo "========================================"
echo "   LoanEase Unified Backend Startup"
echo "========================================"
echo

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Creating .env file from example..."
    cp env.example .env
    echo
    echo "IMPORTANT: Edit .env file and add your GROQ_API_KEY"
    echo
    read -p "Press Enter to continue..."
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create necessary directories
mkdir -p keys models

# Start the unified backend
echo
echo "========================================"
echo "Starting LoanEase Unified Backend"
echo "========================================"
echo
echo "API will be available at: http://localhost:8000"
echo "Documentation at: http://localhost:8000/docs"
echo
echo "Press Ctrl+C to stop the server"
echo

uvicorn main:app --reload --host 0.0.0.0 --port 8000
