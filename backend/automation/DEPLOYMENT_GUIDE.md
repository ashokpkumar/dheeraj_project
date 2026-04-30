# Docker Build & Deploy Guide

This guide shows how to build and deploy Docker containers with custom roles and names.

## Quick Start

### Windows
```bash
# Build and deploy orchestrator
.\build-and-deploy.bat orchestrator orchestrator_main

# Build and deploy worker
.\build-and-deploy.bat worker worker_1
.\build-and-deploy.bat worker worker_2
.\build-and-deploy.bat worker worker_3
```

### macOS/Linux
```bash
# Build and deploy orchestrator
./build-and-deploy.sh orchestrator orchestrator_main

# Build and deploy worker
./build-and-deploy.sh worker worker_1
./build-and-deploy.sh worker worker_2
./build-and-deploy.sh worker worker_3
```

---

## Setup Prerequisites

### 1. Create Docker Network (One Time)
```bash
docker network create automation_network
```

### 2. Ensure Redis is Running
```bash
# Option A: Run Redis in Docker
docker run -d --name automation_redis \
  -p 6379:6379 \
  --network automation_network \
  redis:7-alpine

# Option B: Use existing Redis
# Update CELERY_BROKER_URL in .env
```

### 3. Configure .env File
```bash
# Copy template
cp .env.example .env

# Edit .env with your settings
# Critical settings:
DB_HOST=localhost          # Your MS SQL Server
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=YourPassword
CELERY_BROKER_URL=redis://automation_redis:6379/0
```

---

## Deployment Scenarios

### Scenario A: Single Server (All-in-One)

Start all services on one machine:

```bash
# 1. Start Redis
docker run -d --name automation_redis \
  -p 6379:6379 \
  --network automation_network \
  redis:7-alpine

# 2. Start API Server (Orchestrator)
.\build-and-deploy.bat orchestrator orchestrator_main serve

# 3. Start Celery Worker
.\build-and-deploy.bat worker worker_1 worker

# 4. Start Celery Beat (Scheduler)
.\build-and-deploy.bat orchestrator orchestrator_main beat

# 5. Start Flower (Monitoring)
.\build-and-deploy.bat orchestrator orchestrator_main flower

# 6. Access Services
# API: http://localhost:8000
# Flower: http://localhost:5555
```

### Scenario B: Distributed (Multiple Workers)

```bash
# 1. Start Orchestrator with API + Beat + Worker
.\build-and-deploy.bat orchestrator orchestrator_main serve
.\build-and-deploy.bat orchestrator orchestrator_main beat
.\build-and-deploy.bat orchestrator orchestrator_main worker

# 2. Scale with additional workers
.\build-and-deploy.bat worker worker_1 worker
.\build-and-deploy.bat worker worker_2 worker
.\build-and-deploy.bat worker worker_3 worker

# 3. Start Monitoring
.\build-and-deploy.bat orchestrator orchestrator_main flower

# 4. All workers connect to same Redis and database
# Load is distributed automatically
```

### Scenario C: Development (Quick Start)

```bash
# All-in-one command for testing
.\build-and-deploy.bat orchestrator dev serve
```

---

## Commands Reference

### Build and Deploy Syntax
```bash
.\build-and-deploy.bat <role> <node_name> [command]
```

**Parameters:**
- `<role>`: `orchestrator` or `worker` (determines IS_ORCHESTRATOR env var)
- `<node_name>`: Custom name (e.g., `main`, `worker_1`, `prod_east`)
- `[command]`: Optional command to run
  - `serve` - Start API server (default)
  - `worker` - Start Celery worker
  - `beat` - Start Celery Beat scheduler
  - `flower` - Start Flower monitoring
  - `shell` - Start Django shell
  - `config` - Show configuration

### Container Naming
The container will be named: `automation_<node_name>`

Examples:
- `.\build-and-deploy.bat orchestrator main serve`
  → Container: `automation_main`
  
- `.\build-and-deploy.bat worker node1 worker`
  → Container: `automation_node1`

---

## Typical Workflow

### Initial Setup
```bash
# 1. Create network
docker network create automation_network

# 2. Start Redis
docker run -d --name automation_redis \
  -p 6379:6379 \
  --network automation_network \
  redis:7-alpine

# 3. Update .env file
# - Set database credentials
# - Set Redis URL: redis://automation_redis:6379/0

# 4. Build main orchestrator
.\build-and-deploy.bat orchestrator main serve

# Wait a moment, then init database
docker exec -it automation_main python manage.py migrate
docker exec -it automation_main python manage.py createsuperuser
```

### Start Background Services
```bash
# Start scheduler
.\build-and-deploy.bat orchestrator main beat

# Start workers
.\build-and-deploy.bat worker w1 worker
.\build-and-deploy.bat worker w2 worker

# Start monitoring
.\build-and-deploy.bat orchestrator main flower
```

### Access Services
- **API**: http://localhost:8000
- **Admin**: http://localhost:8000/admin
- **Flower**: http://localhost:5555

---

## Managing Containers

### View All Containers
```bash
docker ps -a
```

### View Specific Container
```bash
docker ps | findstr automation
```

### View Logs
```bash
# Real-time logs
docker logs -f automation_main

# Last 50 lines
docker logs automation_main --tail 50

# With timestamps
docker logs -f automation_main --timestamps
```

### Execute Commands
```bash
# Open shell
docker exec -it automation_main bash

# Run Django command
docker exec automation_main python manage.py shell

# Run Python command
docker exec automation_main python -c "print('hello')"
```

### Stop Container
```bash
docker stop automation_main
```

### Start Container
```bash
docker start automation_main
```

### Remove Container
```bash
docker rm automation_main
```

### Restart Container
```bash
docker restart automation_main
```

---

## Monitoring

### Flower Dashboard
Access http://localhost:5555 to view:
- Active tasks
- Worker status
- Task history
- System statistics

### Database Queries
```bash
docker exec -it automation_main python manage.py shell

>>> from rule_engine.models import RuleEngine
>>> RuleEngine.objects.all()
```

### Redis Status
```bash
docker exec automation_redis redis-cli

> ping
PONG

> keys *
> info memory
```

---

## Production Deployment

### Multi-Node Production Setup

**Node 1 (Orchestrator + API):**
```bash
docker network create automation_prod

.\build-and-deploy.bat orchestrator prod-main serve
```

**Scheduler Node (separate):**
```bash
.\build-and-deploy.bat orchestrator prod-beat beat
```

**Worker Nodes:**
```bash
.\build-and-deploy.bat worker prod-w1 worker
.\build-and-deploy.bat worker prod-w2 worker
.\build-and-deploy.bat worker prod-w3 worker
```

**Monitoring:**
```bash
.\build-and-deploy.bat orchestrator prod-flower flower
```

### Production Environment Variables (.env)
```
DEBUG=False
SECRET_KEY=your-long-random-secret-key
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# Database
DB_HOST=prod-db-server
DB_PORT=1433
DB_USER=prod_user
DB_PASSWORD=strong-password-here

# Redis (external)
CELERY_BROKER_URL=redis://prod-redis-server:6379/0
CELERY_RESULT_BACKEND=redis://prod-redis-server:6379/0

# Orchestrator settings
IS_ORCHESTRATOR=True  (only on beat/main nodes)
```

---

## Troubleshooting

### Container fails to start
```bash
# Check logs
docker logs automation_main

# Common issues:
# - Redis not accessible: Check CELERY_BROKER_URL in .env
# - Database connection: Check DB_* variables in .env
# - Migrations failed: Run manually in orchestrator container
```

### Tasks not running
```bash
# Check Celery worker
docker logs -f automation_w1

# Check Beat scheduler
docker logs -f automation_prod-beat

# Check Redis connection
docker exec automation_redis redis-cli ping
```

### API not responding
```bash
# Check API logs
docker logs -f automation_main

# Test endpoint
curl http://localhost:8000/api/system/status/

# Check if port 8000 is in use
netstat -ano | findstr :8000
```

### Database migrations fail
```bash
# Run manually
docker exec automation_main python manage.py migrate --verbose

# Check migration status
docker exec automation_main python manage.py migrate --plan
```

---

## Clean Up

### Stop All Containers
```bash
docker stop $(docker ps -q)
```

### Remove All Automation Containers
```bash
docker ps -a | findstr automation_ | awk '{print $1}' | xargs docker rm
```

### Remove All Automation Images
```bash
docker images | findstr automation | awk '{print $3}' | xargs docker rmi
```

### Full Reset
```bash
# Remove containers
docker ps -a | findstr automation | awk '{print $1}' | xargs docker rm

# Remove images
docker images | findstr automation | awk '{print $3}' | xargs docker rmi

# Remove network
docker network rm automation_network
```

---

## Advanced Usage

### Custom Image Names
```bash
# Build with specific image name
docker build \
  --build-arg ROLE=orchestrator \
  --build-arg NODE_NAME=prod \
  --build-arg IS_ORCHESTRATOR=True \
  -t automation:prod \
  .

# Use custom image in docker run
docker run -d --name automation_prod \
  -p 8000:8000 \
  --env-file .env \
  automation:prod \
  serve
```

### Environment Override
```bash
# Pass environment variables at runtime
docker run -d --name automation_custom \
  -p 8000:8000 \
  --env-file .env \
  -e DEBUG=True \
  -e IS_ORCHESTRATOR=False \
  automation:worker \
  worker
```

### Volume Mounting
```bash
# Mount local code for development
docker run -d --name automation_dev \
  -v C:\Path\To\Code:/app \
  automation:orchestrator \
  serve
```

---

## CI/CD Integration

### GitHub Actions Example
```yaml
name: Build and Deploy

on: [push]

jobs:
  deploy:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Build Orchestrator
        run: .\build-and-deploy.bat orchestrator prod serve
      
      - name: Build Workers
        run: |
          .\build-and-deploy.bat worker prod-w1 worker
          .\build-and-deploy.bat worker prod-w2 worker
```

---

## Support & Debugging

For issues, check:
1. Container logs: `docker logs -f <container_name>`
2. Environment variables: `docker exec <container> env`
3. Configuration: `docker exec <container> python manage.py show_config`
4. Redis connection: `docker exec <redis> redis-cli ping`
