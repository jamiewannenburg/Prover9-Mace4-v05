#!/bin/bash

# Enable BuildKit
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# Build the image with BuildKit enabled
docker compose build

echo "Build complete! To start the container, run:"
echo "docker compose up -d"
echo ""
echo "Then access the application at http://localhost:8080" 