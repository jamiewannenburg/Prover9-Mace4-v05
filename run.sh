#!/bin/bash

# Prover9-Mace4 Web UI launcher script

# Create saved directory if it doesn't exist
mkdir -p saved

# Check if Docker is installed
if command -v docker &> /dev/null &> /dev/null; then
    echo "Docker is installed. Starting with Docker..."
    docker compose up -d
    
    echo ""
    echo "Prover9-Mace4 Web UI is now running!"
    echo "Open your browser and go to: http://localhost:8080"
    echo ""
    echo "To stop the app, run: docker compose down"
    
elif command -v python3 &> /dev/null; then
    echo "Docker not found. Checking for Python environment..."
    
    # Check if virtual environment exists, create if not
    if [ ! -d "venv" ]; then
        echo "Creating Python virtual environment..."
        python3 -m venv venv
    fi
    
    # Activate the virtual environment
    source venv/bin/activate
    
    # Install dependencies if not already installed
    if [ ! -f "venv/.requirements-installed" ]; then
        echo "Installing requirements..."
        pip install -r requirements.txt
        touch venv/.requirements-installed
    fi
    
    # Run the app
    echo "Starting the app with Flask..."
    python flask_app.py --production
    
else
    echo "Error: Neither Docker nor Python 3 is available."
    echo "Please install either Docker and docker-compose, or Python 3."
    exit 1
fi 