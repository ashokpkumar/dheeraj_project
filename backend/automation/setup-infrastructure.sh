#!/bin/bash

# Setup script for automation infrastructure
# Creates Docker network and starts Redis

echo ""
echo "========================================"
echo "  Automation Infrastructure Setup"
echo "========================================"
echo ""

# Check if network exists
if docker network inspect automation_network &> /dev/null; then
  echo "Docker network already exists: automation_network"
else
  echo "Creating Docker network: automation_network..."
  docker network create automation_network
  echo "Docker network created"
fi
echo ""

# Check if Redis container exists
if docker ps -a --format '{{.Names}}' | grep -q '^automation_redis$'; then
  echo "Redis container already exists"
  echo "Checking if it's running..."
  if docker ps --format '{{.Names}}' | grep -q '^automation_redis$'; then
    echo "Redis is running"
  else
    echo "Starting Redis..."
    docker start automation_redis
  fi
else
  echo "Starting Redis container..."
  docker run -d --name automation_redis \
    -p 6379:6379 \
    --network automation_network \
    redis:7-alpine

  echo "Redis container started"
  echo "Waiting for Redis to be ready..."
  sleep 3
fi

echo ""
echo "========================================"
echo "  Infrastructure Ready"
echo "========================================"
echo "Network: automation_network"
echo "Redis: automation_redis (port 6379)"
echo ""
echo "Next steps:"
echo "  1. Update your .env file with database credentials"
echo "  2. Build services: ./build-and-deploy.sh orchestrator main serve"
echo "  3. Run migrations: docker exec -it automation_main python manage.py migrate"
echo ""
