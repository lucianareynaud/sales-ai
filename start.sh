#!/bin/bash
# Whisper Transcription App Startup Script

set -e  # Exit on any error

# Print header
echo "========================================"
echo "Whisper Transcription App Startup"
echo "========================================"

# Check for Docker CLI
if ! command -v docker &>/dev/null; then
    echo "❌ Error: Docker CLI is required but not found"
    echo "Please install Docker CLI and try again"
    exit 1
fi

# Check for Colima or Docker Desktop
DOCKER_RUNNING=false

# Check if Colima is installed and running
if command -v colima &>/dev/null; then
    COLIMA_STATUS=$(colima status 2>/dev/null | grep "Running" || echo "")
    if [[ -n "$COLIMA_STATUS" ]]; then
        DOCKER_RUNNING=true
        echo "✅ Colima is running"
    else
        echo "⚠️ Colima is installed but not running"
        echo "Starting Colima..."
        if [[ -f "colima-config.yaml" ]]; then
            echo "Colima config file found, but --config flag not supported in this version."
            echo "Using configuration parameters directly..."
            colima start --cpu 4 --memory 8 --disk 60 --mount-type virtiofs || { echo "❌ Failed to start Colima. Please start it manually with 'colima start'"; exit 1; }
        else
            echo "Using default Colima configuration with performance settings..."
            colima start --cpu 4 --memory 8 --disk 60 --mount-type virtiofs || { echo "❌ Failed to start Colima. Please start it manually with 'colima start'"; exit 1; }
        fi
        DOCKER_RUNNING=true
    fi
else
    # If Colima is not installed, check if Docker Desktop might be running
    if docker info &>/dev/null; then
        DOCKER_RUNNING=true
        echo "✅ Docker is running (possibly via Docker Desktop)"
    else
        echo "❌ Error: No running Docker environment detected"
        echo "Please install and start Colima with:"
        echo "  brew install colima docker"
        echo "  colima start"
        echo "Or start Docker Desktop if you prefer"
        exit 1
    fi
fi

# Check for Docker Compose
if ! (command -v docker-compose &>/dev/null || docker compose version &>/dev/null); then
    echo "❌ Error: Docker Compose is required but not found"
    echo "Please install Docker Compose and try again"
    exit 1
fi

echo "✅ Docker and Docker Compose are available"

# Create uploads directory if it doesn't exist
if [[ ! -d "uploads" ]]; then
    echo "Creating uploads directory..."
    mkdir -p uploads
fi

# Start the application with Docker
echo "Starting application with Docker Compose..."
# Use the new docker compose syntax if available
if docker compose version &>/dev/null; then
    docker compose up -d
else
    docker-compose up -d
fi

echo ""
echo "✅ Whisper Transcription App is running!"
echo "Open http://localhost:8081 in your browser"
echo ""
echo "To view logs: docker compose logs -f (or docker-compose logs -f)"
echo "To stop: docker compose down (or docker-compose down)" 