#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=================================${NC}"
echo -e "${GREEN}Automation Service Startup${NC}"
echo -e "${GREEN}=================================${NC}"
echo "Node Name: $NODE_NAME"
echo "Role: $ROLE"
echo "IS_ORCHESTRATOR: $IS_ORCHESTRATOR"
echo ""

# Wait for Redis
echo -e "${YELLOW}Waiting for Redis...${NC}"
redis_host=automation_redis
redis_port=${REDIS_PORT:-6379}
while ! nc -z $redis_host $redis_port 2>/dev/null; do
  echo "Redis not ready, waiting..."
  sleep 1
done
echo -e "${GREEN}✓ Redis is ready${NC}"

# Wait for Database
echo -e "${YELLOW}Waiting for Database...${NC}"
# Optional: Add database check here

# Run migrations (only on orchestrator to avoid conflicts)
# if [ "$IS_ORCHESTRATOR" = "True" ] || [ "$IS_ORCHESTRATOR" = "true" ]; then
#   echo -e "${YELLOW}Running migrations...${NC}"
#   python manage.py migrate --noinput || true
#   python manage.py collectstatic --noinput || true
#   echo -e "${GREEN}✓ Migrations completed${NC}"
# fi

# Execute the command passed to docker
echo -e "${YELLOW}Starting $ROLE service...${NC}"
echo -e "${GREEN}=================================${NC}"

# If no command specified, default to 'serve'
if [ $# -eq 0 ]; then
  exec python manage.py show_config --verbose
  set -- "serve"
fi

# Route based on command
case "$1" in
  "serve")
    echo "Starting API server on 0.0.0.0:8000"
    exec gunicorn automation.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 120
    ;;
  "worker")
    echo "Starting Celery worker"
    exec celery -A automation worker --loglevel=info --concurrency=4
    ;;
  "beat")
    echo "Starting Celery Beat scheduler"
    if [ "$IS_ORCHESTRATOR" = "True" ] || [ "$IS_ORCHESTRATOR" = "true" ]; then
      exec celery -A automation beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    else
      echo -e "${RED}ERROR: Celery Beat can only run in orchestrator mode!${NC}"
      exit 1
    fi
    ;;
  "flower")
    echo "Starting Flower monitoring UI"
    exec celery -A automation flower --port=5555
    ;;
  "shell")
    echo "Starting Django shell"
    exec python manage.py shell
    ;;
  "config")
    echo "Showing configuration"
    exec python manage.py show_config --verbose
    ;;
  *)
    echo "Running command: $@"
    exec "$@"
    ;;
esac
