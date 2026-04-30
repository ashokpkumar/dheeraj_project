# Docker Build & Deploy Cheat Sheet

## 🚀 Quick Start

### Windows
```powershell
# Setup infrastructure (one time)
.\setup-infrastructure.bat

# Build and start orchestrator
.\build-and-deploy.bat orchestrator main serve

# Build and start worker
.\build-and-deploy.bat worker w1 worker

# Build and start scheduler
.\build-and-deploy.bat orchestrator main beat

# Build and start monitoring
.\build-and-deploy.bat orchestrator main flower
```

### macOS/Linux
```bash
# Setup infrastructure (one time)
./setup-infrastructure.sh

# Build and start orchestrator
./build-and-deploy.sh orchestrator main serve

# Build and start worker
./build-and-deploy.sh worker w1 worker
```

---

## 🔧 Common Commands

### Build & Deploy
```bash
# Syntax: build-and-deploy.bat <role> <node_name> [command]

# API Server
.\build-and-deploy.bat orchestrator api serve

# Celery Worker
.\build-and-deploy.bat worker w1 worker

# Celery Scheduler
.\build-and-deploy.bat orchestrator scheduler beat

# Monitoring UI
.\build-and-deploy.bat orchestrator flower flower

# Shell
.\build-and-deploy.bat orchestrator shell shell
```

### View Containers
```bash
# All containers
docker ps -a

# Running containers
docker ps

# With status
docker ps --all --format "table {{.Names}}\t{{.Status}}"
```

### Logs
```bash
# Real-time logs
docker logs -f automation_main

# Last 50 lines
docker logs automation_main --tail 50

# With timestamps
docker logs -t automation_main
```

### Execute Commands
```bash
# Django shell
docker exec -it automation_main python manage.py shell

# Run migration
docker exec automation_main python manage.py migrate

# Create user
docker exec -it automation_main python manage.py createsuperuser

# Show config
docker exec automation_main python manage.py show_config
```

### Container Management
```bash
# Stop
docker stop automation_main

# Start
docker start automation_main

# Restart
docker restart automation_main

# Remove
docker rm automation_main

# View details
docker inspect automation_main
```

---

## 📊 Access Services

| Service | URL | Purpose |
|---------|-----|---------|
| **API** | http://localhost:8000 | REST API |
| **Admin** | http://localhost:8000/admin | Django Admin |
| **Flower** | http://localhost:5555 | Task Monitoring |
| **Redis** | localhost:6379 | Message Broker |

---

## 🏗️ Deployment Scenarios

### Single Machine (All-in-One)
```bash
# 1. Setup
.\setup-infrastructure.bat

# 2. API Server
.\build-and-deploy.bat orchestrator main serve

# 3. Scheduler
.\build-and-deploy.bat orchestrator main beat

# 4. Worker
.\build-and-deploy.bat worker w1 worker

# 5. Monitoring
.\build-and-deploy.bat orchestrator main flower
```

### Distributed (Multiple Workers)
```bash
# Orchestrator nodes
.\build-and-deploy.bat orchestrator main serve
.\build-and-deploy.bat orchestrator main beat

# Worker nodes (scale as needed)
.\build-and-deploy.bat worker w1 worker
.\build-and-deploy.bat worker w2 worker
.\build-and-deploy.bat worker w3 worker

# Monitoring
.\build-and-deploy.bat orchestrator main flower
```

---

## 🔍 Debugging

### Check Container Status
```bash
docker ps -a | findstr automation
```

### View Error Logs
```bash
docker logs automation_main | findstr -i error
```

### Test Redis Connection
```bash
docker exec automation_redis redis-cli ping
# Should return: PONG
```

### Test Database Connection
```bash
docker exec automation_main python manage.py dbshell
```

### Check Configuration
```bash
docker exec automation_main python manage.py show_config --verbose
```

---

## 📝 Environment Variables (.env)

```env
# Django
DEBUG=False
SECRET_KEY=your-secret-key

# Database
DB_HOST=localhost
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=password

# Redis/Celery
CELERY_BROKER_URL=redis://automation_redis:6379/0
CELERY_RESULT_BACKEND=redis://automation_redis:6379/0

# Orchestrator
IS_ORCHESTRATOR=True
```

---

## 🎯 Image Names

**Format:** `automation:<role>`

- `automation:orchestrator` - Orchestrator image
- `automation:worker` - Worker image

---

## 🧹 Cleanup

### Stop All
```bash
docker stop $(docker ps -q)
```

### Remove All Automation Containers
```bash
docker ps -a | findstr automation_ | {for /f "tokens=1" %i in ('findstr automation_') do docker rm %i}
```

### Remove All Images
```bash
for /f "tokens=3" %i in ('docker images ^| findstr automation') do docker rmi %i
```

### Full Reset
```bash
# Stop and remove
docker stop $(docker ps -q) && docker rm $(docker ps -aq)

# Remove images
docker rmi automation:orchestrator automation:worker

# Remove network
docker network rm automation_network
```

---

## 🚨 Common Issues

### Port Already in Use
```bash
# Check what's using port 8000
netstat -ano | findstr :8000

# Kill the process (Windows)
taskkill /PID <PID> /F

# Or use different port in docker run
docker run -p 9000:8000 ...
```

### Redis Connection Failed
```bash
# Ensure Redis is running
docker ps | findstr automation_redis

# Check Redis logs
docker logs automation_redis

# Restart Redis
docker restart automation_redis
```

### Database Connection Failed
```bash
# Check .env database settings
cat .env | findstr DB_

# Verify database is accessible
docker exec automation_main python manage.py dbshell
```

### Migrations Failed
```bash
# Check migration status
docker exec automation_main python manage.py migrate --plan

# Run with verbose output
docker exec automation_main python manage.py migrate --verbose
```

---

## 📊 Monitoring Commands

### Celery Tasks
```bash
# In Django shell
docker exec -it automation_main python manage.py shell

>>> from celery_app import app
>>> app.control.inspect().active()
>>> app.control.inspect().stats()
```

### Redis Info
```bash
docker exec automation_redis redis-cli info
docker exec automation_redis redis-cli dbsize
docker exec automation_redis redis-cli keys '*'
```

### Database Stats
```bash
docker exec -it automation_main python manage.py shell

>>> from django.db import connection
>>> cursor = connection.cursor()
>>> cursor.execute("SELECT COUNT(*) FROM rule_engine_ruleengine")
>>> cursor.fetchone()
```

---

## 🔄 Update & Restart

### After Code Changes
```bash
# Rebuild image
docker build -t automation:orchestrator .

# Restart container
docker restart automation_main
```

### Update Dependencies
```bash
# Rebuild without cache
docker build --no-cache -t automation:orchestrator .

# Restart all containers
docker restart automation_main automation_w1 automation_w2
```

---

## 🎓 Learning Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose](https://docs.docker.com/compose/)
- [Celery Documentation](https://docs.celeryproject.io/)
- [Django Deployment Guide](https://docs.djangoproject.com/en/stable/howto/deployment/)
