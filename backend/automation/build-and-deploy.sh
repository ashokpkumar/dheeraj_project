#!/bin/bash

# Docker Build and Deploy Helper
# Usage:
#   ./build-and-deploy.sh orchestrator orchestrator_main
#   ./build-and-deploy.sh worker worker_1
#   ./build-and-deploy.sh worker worker_2

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Arguments
ROLE=${1:-orchestrator}
NODE_NAME=${2:-${ROLE}_1}
COMMAND=${3:-serve}

# Validate role
if [[ "$ROLE" != "orchestrator" && "$ROLE" != "worker" ]]; then
  echo -e "${RED}Error: Role must be 'orchestrator' or 'worker'${NC}"
  echo "Usage: ./build-and-deploy.sh <role> <node_name> [command]"
  echo "  Roles: orchestrator, worker"
  echo "  Commands: serve, worker, beat, flower, shell, config"
  exit 1
fi

# Set IS_ORCHESTRATOR based on role
if [ "$ROLE" = "orchestrator" ]; then
  IS_ORCHESTRATOR=True
else
  IS_ORCHESTRATOR=False
fi

IMAGE_NAME="automation:${ROLE}"
CONTAINER_NAME="automation_${NODE_NAME}"

# Build container name with command suffix for special services
if [ "$COMMAND" = "beat" ]; then
  CONTAINER_NAME="automation_${NODE_NAME}_beat"
elif [ "$COMMAND" = "flower" ]; then
  CONTAINER_NAME="automation_${NODE_NAME}_flower"
elif [ "$COMMAND" = "worker" ]; then
  CONTAINER_NAME="automation_${NODE_NAME}_worker"
fi

echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Docker Build & Deploy${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo -e "${YELLOW}Role:${NC} $ROLE"
echo -e "${YELLOW}Node Name:${NC} $NODE_NAME"
echo -e "${YELLOW}Container Name:${NC} $CONTAINER_NAME"
echo -e "${YELLOW}Image Name:${NC} $IMAGE_NAME"
echo -e "${YELLOW}IS_ORCHESTRATOR:${NC} $IS_ORCHESTRATOR"
echo -e "${YELLOW}Command:${NC} $COMMAND"
echo ""

# Step 1: Build Docker image
echo -e "${BLUE}Step 1: Building Docker image...${NC}"
docker build \
  --build-arg ROLE=$ROLE \
  --build-arg NODE_NAME=$NODE_NAME \
  --build-arg IS_ORCHESTRATOR=$IS_ORCHESTRATOR \
  -t $IMAGE_NAME \
  .

echo -e "${GREEN}✓ Docker image built: $IMAGE_NAME${NC}"
echo ""

# Step 2: Stop existing container if running
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo -e "${BLUE}Step 2: Stopping existing container...${NC}"
  docker stop $CONTAINER_NAME || true
  docker rm $CONTAINER_NAME || true
  echo -e "${GREEN}✓ Existing container stopped and removed${NC}"
  echo ""
else
  echo -e "${BLUE}Step 2: No existing container found${NC}"
  echo ""
fi

# Step 3: Run container
echo -e "${BLUE}Step 3: Starting new container...${NC}"

if [ "$COMMAND" = "serve" ]; then
  # API Server
  docker run -d \
    --name $CONTAINER_NAME \
    -p 8000:8000 \
    --env-file .env \
    -e ROLE=$ROLE \
    -e NODE_NAME=$NODE_NAME \
    -e IS_ORCHESTRATOR=$IS_ORCHESTRATOR \
    --network automation_network \
    -v $(pwd):/app \
    $IMAGE_NAME \
    serve
    
  echo -e "${GREEN}✓ Container started in API server mode${NC}"
  echo -e "${YELLOW}API Available at: http://localhost:8000${NC}"
  
elif [ "$COMMAND" = "worker" ]; then
  # Celery Worker
  docker run -d \
    --name $CONTAINER_NAME \
    --env-file .env \
    -e ROLE=$ROLE \
    -e NODE_NAME=$NODE_NAME \
    -e IS_ORCHESTRATOR=$IS_ORCHESTRATOR \
    --network automation_network \
    -v $(pwd):/app \
    $IMAGE_NAME \
    worker
    
  echo -e "${GREEN}✓ Container started in Celery worker mode${NC}"
  
elif [ "$COMMAND" = "beat" ]; then
  # Celery Beat (Scheduler)
  if [ "$IS_ORCHESTRATOR" != "True" ]; then
    echo -e "${RED}Error: Celery Beat can only run in orchestrator mode${NC}"
    exit 1
  fi
  
  docker run -d \
    --name $CONTAINER_NAME \
    --env-file .env \
    -e ROLE=$ROLE \
    -e NODE_NAME=$NODE_NAME \
    -e IS_ORCHESTRATOR=$IS_ORCHESTRATOR \
    --network automation_network \
    -v $(pwd):/app \
    $IMAGE_NAME \
    beat
    
  echo -e "${GREEN}✓ Container started in Celery Beat scheduler mode${NC}"
  
elif [ "$COMMAND" = "flower" ]; then
  # Flower (Monitoring)
  docker run -d \
    --name $CONTAINER_NAME \
    -p 5555:5555 \
    --env-file .env \
    -e ROLE=$ROLE \
    -e NODE_NAME=$NODE_NAME \
    -e IS_ORCHESTRATOR=$IS_ORCHESTRATOR \
    --network automation_network \
    -v $(pwd):/app \
    $IMAGE_NAME \
    flower
    
  echo -e "${GREEN}✓ Container started in Flower monitoring mode${NC}"
  echo -e "${YELLOW}Flower UI Available at: http://localhost:5555${NC}"
  
else
  # Custom command
  docker run -d \
    --name $CONTAINER_NAME \
    --env-file .env \
    -e ROLE=$ROLE \
    -e NODE_NAME=$NODE_NAME \
    -e IS_ORCHESTRATOR=$IS_ORCHESTRATOR \
    --network automation_network \
    -v $(pwd):/app \
    $IMAGE_NAME \
    $COMMAND
    
  echo -e "${GREEN}✓ Container started with command: $COMMAND${NC}"
fi

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Container Details${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo -e "${YELLOW}Container Name:${NC} $CONTAINER_NAME"
echo -e "${YELLOW}Image:${NC} $IMAGE_NAME"
echo -e "${YELLOW}Status:${NC}" $(docker ps --format "{{.Names}} {{.Status}}" | grep $CONTAINER_NAME)
echo ""
echo -e "${BLUE}Useful Commands:${NC}"
echo "  View logs:    ${GREEN}docker logs -f $CONTAINER_NAME${NC}"
echo "  Stop:         ${GREEN}docker stop $CONTAINER_NAME${NC}"
echo "  Start:        ${GREEN}docker start $CONTAINER_NAME${NC}"
echo "  Remove:       ${GREEN}docker rm $CONTAINER_NAME${NC}"
echo "  Shell:        ${GREEN}docker exec -it $CONTAINER_NAME bash${NC}"
echo ""
