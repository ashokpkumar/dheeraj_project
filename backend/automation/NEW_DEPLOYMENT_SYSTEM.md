# New Docker Deployment System - Summary

## 🎯 What's New

Your Docker setup has been completely transformed to support flexible, role-based builds and deployments with custom naming.

### Key Features

✅ **Build-time Arguments** - Specify role (orchestrator/worker) during build  
✅ **Custom Container Names** - Name containers like `orchestrator_main`, `worker_1`, `worker_2`  
✅ **Smart Entrypoint** - Route to different services based on command  
✅ **Flexible Deployment** - Build, deploy, and start with single commands  
✅ **Environment-aware** - Automatic IS_ORCHESTRATOR configuration  

---

## 🚀 Quick Start

### Windows

```powershell
# 1. Setup infrastructure (one time)
.\setup-infrastructure.bat

# 2. Update .env with your database credentials
# Edit C:\...\.env

# 3. Build and start orchestrator
.\build-and-deploy.bat orchestrator main serve

# 4. Wait a few seconds, then run migrations
docker exec -it automation_main python manage.py migrate
docker exec -it automation_main python manage.py createsuperuser

# 5. Start background services
.\build-and-deploy.bat orchestrator main beat
.\build-and-deploy.bat worker w1 worker
.\build-and-deploy.bat orchestrator main flower

# 6. Access services
# API:     http://localhost:8000
# Admin:   http://localhost:8000/admin
# Flower:  http://localhost:5555
```

### macOS/Linux

```bash
./setup-infrastructure.sh
./build-and-deploy.sh orchestrator main serve
docker exec -it automation_main python manage.py migrate
docker exec -it automation_main python manage.py createsuperuser
./build-and-deploy.sh orchestrator main beat
./build-and-deploy.sh worker w1 worker
./build-and-deploy.sh orchestrator main flower
```

---

## 📋 Files Changed/Created

### New Files

| File | Purpose |
|------|---------|
| `build-and-deploy.bat` | Windows deployment script |
| `build-and-deploy.sh` | Linux/macOS deployment script |
| `setup-infrastructure.bat` | Windows infrastructure setup |
| `setup-infrastructure.sh` | Linux/macOS infrastructure setup |
| `DEPLOYMENT_GUIDE.md` | Comprehensive deployment guide |
| `CHEATSHEET.md` | Quick reference commands |

### Updated Files

| File | Changes |
|------|---------|
| `Dockerfile` | Added build arguments (ROLE, NODE_NAME, IS_ORCHESTRATOR) |
| `entrypoint.sh` | Added intelligent command routing |
| `Makefile` | Added new build/deploy commands |

---

## 🔧 Build Arguments

The Dockerfile now accepts these build arguments:

```dockerfile
ARG ROLE=orchestrator              # orchestrator or worker
ARG NODE_NAME=default              # Custom node name
ARG IS_ORCHESTRATOR=True           # true/false for orchestrator mode
```

These automatically set environment variables in the container.

---

## 📱 Deployment Examples

### Example 1: Single Machine (All Services)

```bash
# Setup
.\setup-infrastructure.bat

# Main orchestrator with API
.\build-and-deploy.bat orchestrator main serve

# Database setup
docker exec -it automation_main python manage.py migrate
docker exec -it automation_main python manage.py createsuperuser

# Add services
.\build-and-deploy.bat orchestrator main beat      # Scheduler
.\build-and-deploy.bat worker w1 worker            # Worker 1
.\build-and-deploy.bat worker w2 worker            # Worker 2
.\build-and-deploy.bat orchestrator main flower    # Monitoring

# Services running:
# - API Server: http://localhost:8000
# - Flower: http://localhost:5555
# - Workers: 2 (w1, w2)
# - Scheduler: Active
```

### Example 2: Scale Workers

```bash
# Start 5 workers
.\build-and-deploy.bat worker w1 worker
.\build-and-deploy.bat worker w2 worker
.\build-and-deploy.bat worker w3 worker
.\build-and-deploy.bat worker w4 worker
.\build-and-deploy.bat worker w5 worker

# All share same Redis and database
# Load automatically distributed
```

### Example 3: Production Multi-Node

```bash
# Node 1: Orchestrator (main API)
.\build-and-deploy.bat orchestrator prod-api serve

# Node 2: Scheduler
.\build-and-deploy.bat orchestrator prod-scheduler beat

# Nodes 3-5: Workers
.\build-and-deploy.bat worker prod-w1 worker
.\build-and-deploy.bat worker prod-w2 worker
.\build-and-deploy.bat worker prod-w3 worker

# Node 6: Monitoring
.\build-and-deploy.bat orchestrator prod-flower flower
```

---

## 🎮 Common Commands

### Deployment

```bash
# Build and deploy with custom name
.\build-and-deploy.bat orchestrator myname serve
.\build-and-deploy.bat worker myworker worker
.\build-and-deploy.bat orchestrator myschedule beat
.\build-and-deploy.bat orchestrator myflower flower
```

### View Status

```bash
# List all containers
docker ps

# Show status with ports
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Show specific container
docker ps | findstr automation_main
```

### View Logs

```bash
# Real-time logs
docker logs -f automation_main

# Last 50 lines with timestamps
docker logs -t automation_main --tail 50

# Specific service
docker logs -f automation_w1
```

### Execute Commands

```bash
# Django shell
docker exec -it automation_main python manage.py shell

# Run migrations
docker exec automation_main python manage.py migrate

# Create user
docker exec -it automation_main python manage.py createsuperuser

# Show configuration
docker exec automation_main python manage.py show_config
```

### Container Management

```bash
# Stop container
docker stop automation_main

# Start container
docker start automation_main

# Restart container
docker restart automation_main

# Remove container
docker rm automation_main

# Remove and rebuild
docker rm automation_main
.\build-and-deploy.bat orchestrator main serve
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│             Docker Desktop / Host Machine               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │         Docker Network: automation_network      │   │
│  ├─────────────────────────────────────────────────┤   │
│  │                                                 │   │
│  │  ┌───────────────┐  ┌────────────────────────┐ │   │
│  │  │  API Server   │  │  Celery Beat Scheduler │ │   │
│  │  │ orchestrator_ │  │  orchestrator_main    │ │   │
│  │  │    main:8000  │  │   (orchestrator only)  │ │   │
│  │  └───────────────┘  └────────────────────────┘ │   │
│  │         │                    │                  │   │
│  │  ┌─────────────────────────────────────────┐   │   │
│  │  │        Celery Workers (Scale)           │   │   │
│  │  │  worker_1 | worker_2 | worker_3 ...    │   │   │
│  │  └─────────────────────────────────────────┘   │   │
│  │         │         │         │                   │   │
│  │  ┌───────────────────────────────────────┐     │   │
│  │  │ Redis Broker                          │     │   │
│  │  │ automation_redis:6379                 │     │   │
│  │  └───────────────────────────────────────┘     │   │
│  │                                                 │   │
│  │  ┌─────────────────────────────────────────┐   │   │
│  │  │ Flower Monitoring UI                    │   │   │
│  │  │ orchestrator_main (flower):5555         │   │   │
│  │  └─────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  All containers use volume mounts and .env config     │
└─────────────────────────────────────────────────────────┘
```

---

## 📊 Container Naming Convention

**Format:** `automation_<node_name>`

### Examples

- **Orchestrator nodes:**
  - `automation_main` - Primary orchestrator
  - `automation_scheduler` - Dedicated scheduler
  - `automation_api` - Dedicated API

- **Worker nodes:**
  - `automation_w1` - Worker 1
  - `automation_w2` - Worker 2
  - `automation_worker_prod` - Production worker

- **Monitoring:**
  - `automation_flower` - Flower UI
  - `automation_redis` - Redis broker (auto-created)

---

## 🔐 Environment Variables

The `.env` file controls container behavior:

```env
# Application
DEBUG=False
SECRET_KEY=your-secret-key

# Database
DB_HOST=localhost
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=password

# Celery/Redis
CELERY_BROKER_URL=redis://automation_redis:6379/0
CELERY_RESULT_BACKEND=redis://automation_redis:6379/0

# Set automatically based on build args (can override):
IS_ORCHESTRATOR=True
ROLE=orchestrator
NODE_NAME=main
```

---

## 🐛 Troubleshooting

### Container won't start
```bash
# Check logs
docker logs automation_main | grep -i error

# Check environment
docker exec automation_main env | grep CELERY
```

### Redis connection error
```bash
# Verify Redis is running
docker ps | findstr automation_redis

# Test connection
docker exec automation_redis redis-cli ping
```

### API port in use
```bash
# Check what's using port 8000
netstat -ano | findstr :8000

# Use different port in docker run
docker run -p 9000:8000 ...
```

### Can't execute docker commands
```bash
# Ensure Docker Desktop is running
# Restart Docker Desktop if needed
```

---

## 📚 Documentation Files

- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Comprehensive guide with scenarios
- **[CHEATSHEET.md](CHEATSHEET.md)** - Quick reference for common commands
- **[DOCKER_README.md](DOCKER_README.md)** - Original detailed documentation
- **[QUICKSTART.md](QUICKSTART.md)** - Quick setup guide

---

## 🚄 Performance Tips

1. **Use external Redis for production** - Not Docker container
2. **Use external database** - Not Docker container
3. **Scale workers** based on CPU/task load
4. **Monitor with Flower** - Check bottlenecks
5. **Use volume mounts** for development, not production
6. **Pin image versions** for production stability

---

## ✨ Next Steps

1. ✅ Update `.env` with database credentials
2. ✅ Run `.\setup-infrastructure.bat`
3. ✅ Build orchestrator: `.\build-and-deploy.bat orchestrator main serve`
4. ✅ Run migrations: `docker exec -it automation_main python manage.py migrate`
5. ✅ Start scheduler: `.\build-and-deploy.bat orchestrator main beat`
6. ✅ Add workers: `.\build-and-deploy.bat worker w1 worker`
7. ✅ Start monitoring: `.\build-and-deploy.bat orchestrator main flower`
8. ✅ Access http://localhost:8000

---

**Happy deploying!** 🚀
