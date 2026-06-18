# 🚀 Getting Started with New Docker Deployment

## Step-by-Step Guide

### Step 1: Prepare Environment File

```bash
# Copy template
cp .env.example .env

# Edit .env (your database credentials)
```

**Update these in `.env`:**
```env
DB_HOST=localhost          # Your MS SQL Server
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=your_password

# Redis (will use Docker container)
CELERY_BROKER_URL=redis://automation_redis:6379/0
```

### Step 2: Setup Docker Infrastructure (Windows)

```powershell
# Create Docker network and start Redis
.\setup-infrastructure.bat
```

**Output:**
```
Docker network already exists: automation_network
Redis is running
```

### Step 3: Build & Start Main Orchestrator

```powershell
# Build orchestrator image and start API server
.\build-and-deploy.bat orchestrator main serve
```

**What this does:**
- ✅ Builds image: `automation:orchestrator`
- ✅ Starts container: `automation_main` (serve = no suffix)
- ✅ Maps port: 8000
- ✅ Sets IS_ORCHESTRATOR=True
- ✅ Exposes API at http://localhost:8000

### Step 4: Initialize Database

```powershell
# Run migrations
docker exec -it automation_main python manage.py migrate

# Create admin user
docker exec -it automation_main python manage.py createsuperuser
```

**This:**
- ✅ Creates database tables
- ✅ Allows you to create admin account

### Step 5: Start Scheduler

```powershell
# Start Celery Beat in separate container
.\build-and-deploy.bat orchestrator main beat
```

**This:**
- ✅ Builds scheduler service
- ✅ Starts container: `automation_main_beat` (beat = _beat suffix)
- ✅ Manages scheduled jobs
- ✅ Syncs jobs from database

### Step 6: Add Workers

```powershell
# Start first worker
.\build-and-deploy.bat worker w1 worker

# Start second worker
.\build-and-deploy.bat worker w2 worker
```

**This:**
- ✅ Builds image: `automation:worker`
- ✅ Creates containers: `automation_w1_worker`, `automation_w2_worker` (_worker suffix)
- ✅ Sets IS_ORCHESTRATOR=False
- ✅ Workers connect to Redis automatically

### Step 7: Start Monitoring

```powershell
# Start Flower UI
.\build-and-deploy.bat orchestrator main flower
```

**This:**
- ✅ Starts container: `automation_main_flower` (_flower suffix)
- ✅ Exposes UI at http://localhost:5555
- ✅ Shows real-time task monitoring

### Step 8: Access Your Services

| Service | URL | Purpose |
|---------|-----|---------|
| **API** | http://localhost:8000 | REST endpoints |
| **Admin** | http://localhost:8000/admin | Django admin |
| **Flower** | http://localhost:5555 | Task monitoring |

---

## 🎯 Verify Everything Works

### Check Containers Running

```powershell
# List all containers
docker ps

# Should show:
# - automation_main (API server, port 8000)
# - automation_main_beat (scheduler)
# - automation_w1_worker (worker 1)
# - automation_w2_worker (worker 2)
# - automation_main_flower (monitoring, port 5555)
# - automation_redis (Redis broker, port 6379)
```

### Test API

```powershell
# In PowerShell
Invoke-WebRequest http://localhost:8000/api/system/status/

# Or in terminal
curl http://localhost:8000/api/system/status/
```

### Check Logs

```powershell
# API server logs
docker logs -f automation_main

# Worker logs
docker logs -f automation_w1

# Scheduler logs
docker logs -f automation_beat
```

### Visit Flower

Open http://localhost:5555 in browser
- Should show: 2 workers connected
- Should show: 0 active tasks
- Should show: System status

---

## 📋 Quick Command Reference

### Build & Deploy

```powershell
# Start orchestrator
.\build-and-deploy.bat orchestrator <name> serve

# Start worker
.\build-and-deploy.bat worker <name> worker

# Start scheduler (orchestrator only)
.\build-and-deploy.bat orchestrator <name> beat

# Start monitoring
.\build-and-deploy.bat orchestrator <name> flower
```

### Container Management

```powershell
# View all
docker ps -a

# View running
docker ps

# View logs
docker logs -f automation_main

# Stop
docker stop automation_main

# Start
docker start automation_main

# Remove
docker rm automation_main
```

### Database Commands

```powershell
# Migrations
docker exec automation_main python manage.py migrate

# Create user
docker exec -it automation_main python manage.py createsuperuser

# Shell
docker exec -it automation_main python manage.py shell

# Configuration
docker exec automation_main python manage.py show_config
```

---

## 🔄 Common Workflows

### Scale to 3 Workers

```powershell
.\build-and-deploy.bat worker w1 worker
.\build-and-deploy.bat worker w2 worker
.\build-and-deploy.bat worker w3 worker
```

### Stop & Rebuild

```powershell
# Stop container
docker stop automation_main

# Remove old container
docker rm automation_main

# Rebuild and start
.\build-and-deploy.bat orchestrator main serve
```

### View All Logs

```powershell
# APILogs
docker logs automation_main

# Worker logs
docker logs automation_w1
docker logs automation_w2

# Scheduler logs
docker logs automation_beat

# Monitoring logs (Flower)
docker logs automation_flower
```

---

## ⚠️ Common Issues

### Port 8000 Already in Use

```powershell
# Find what's using it
netstat -ano | findstr :8000

# Kill the process
taskkill /PID <PID> /F

# Or change port in docker run - add:
-p 9000:8000  (instead of -p 8000:8000)
```

### Redis Connection Failed

```powershell
# Check Redis is running
docker ps | findstr automation_redis

# Check Redis logs
docker logs automation_redis

# Restart Redis
docker stop automation_redis
docker start automation_redis
```

### API Returns 500 Error

```powershell
# Check API logs
docker logs automation_main

# Common issues:
# - Database connection: Check .env DB_* variables
# - Redis connection: Check CELERY_BROKER_URL
# - Migrations not run: Run 'docker exec automation_main python manage.py migrate'
```

### Containers Won't Start

```powershell
# Check detailed error
docker logs automation_main

# Rebuild from scratch
docker rm automation_main
.\build-and-deploy.bat orchestrator main serve

# Check environment
docker exec automation_main env
```

---

## 📊 Complete Setup Summary

**After following all steps, you'll have:**

✅ Docker Network: `automation_network`  
✅ Redis: `automation_redis:6379`  
✅ API Server: `automation_main:8000` (IS_ORCHESTRATOR=True)  
✅ Scheduler: `automation_main_beat` (Celery Beat)  
✅ Workers: `automation_w1_worker`, `automation_w2_worker` (scale as needed)  
✅ Monitoring: `automation_main_flower:5555`  

**Services communicate through:**
- **Redis** for task queue
- **Docker network** for discovery
- **Database** for configuration
- All configuration from **.env** file

---

## 🎓 Next Steps

1. ✅ Create scheduled jobs in Django Admin
2. ✅ Trigger rule engines via API
3. ✅ Monitor execution in Flower
4. ✅ Scale workers based on load
5. ✅ Set up production deployment

---

## 📚 For More Information

- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Advanced scenarios
- [CHEATSHEET.md](CHEATSHEET.md) - Quick command reference
- [API_DOCS.md](API_DOCS.md) - REST API documentation

---

**You're ready to build and deploy!** 🚀

Run this to get started:
```powershell
.\setup-infrastructure.bat
.\build-and-deploy.bat orchestrator main serve
docker exec -it automation_main python manage.py migrate
docker exec -it automation_main python manage.py createsuperuser
.\build-and-deploy.bat orchestrator main beat
.\build-and-deploy.bat worker w1 worker
.\build-and-deploy.bat orchestrator main flower
```

Then visit:
- http://localhost:8000 (API)
- http://localhost:5555 (Monitoring)
