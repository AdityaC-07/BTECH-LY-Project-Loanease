#!/bin/bash

echo "Starting LoanEase Services..."
echo

# Check if .env file exists, if not create example
if [ ! -f .env ]; then
    echo "Creating .env.example file..."
    cat > .env.example << EOL
GROQ_API_KEY=your_key_here
GROQ_MODEL_PRIMARY=llama-3.3-70b-versatile
GROQ_MODEL_FALLBACK=llama-3.1-8b-instant
GROQ_TIMEOUT_SECONDS=8
FALLBACK_MODE=rule_based
FRONTEND_DOMAIN=https://loanease.example.com
EOL
    echo "Please create .env file with your actual API keys"
fi

# Function to start service in background
start_service() {
    local service_name=$1
    local port=$2
    local path=$3
    local module=$4
    
    echo "Starting $service_name (Port $port)..."
    cd "$path"
    python -m uvicorn "$module" --port "$port" --reload &
    sleep 2
}

# Start services in correct order
start_service "KYC Service" 8004 "kyc_backend" "app.main:app"
start_service "Underwriting Service" 8000 "backend" "app.main:app"
start_service "Negotiation Service" 8001 "negotiation_backend" "app.main:app"
start_service "Translation + Groq Service" 8003 "translation_backend" "app.main:app"
start_service "Blockchain Audit Service" 8005 "backend" "blockchain_service:app"
start_service "Pipeline Orchestrator" 8002 "backend" "pipeline:app"

cd ..

echo
echo "All LoanEase services started!"
echo
echo "Service URLs:"
echo "- KYC Service: http://localhost:8004"
echo "- Underwriting: http://localhost:8000"
echo "- Negotiation: http://localhost:8001"
echo "- Translation+Groq: http://localhost:8003"
echo "- Blockchain: http://localhost:8005"
echo "- Pipeline: http://localhost:8002"
echo
echo "Frontend should be started separately with: npm run dev (from frontend folder)"
echo
echo "To stop all services, run: pkill -f 'uvicorn.*LoanEase'"
