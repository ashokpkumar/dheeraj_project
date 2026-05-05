# Docker Build & Deploy Cheat Sheet

## � Batch Scripts (Windows)

All scripts are in the `backend/automation/` directory. Simply double-click or run from PowerShell.

**Available in two formats:**
- `.bat` files - Classic batch scripts (cmd.exe)
- `.ps1` files - PowerShell scripts (more colorful output)

**Running Batch Scripts:**
```powershell
# From PowerShell
.\quick-start.bat
.\status.bat
.\view-logs.bat main

# Or double-click from File Explorer
```

**Running PowerShell Scripts:**
```powershell
# First time setup
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then run
.\quick-start.ps1
.\status.ps1
.\view-logs.ps1 main
```

---

### 1. **setup-infrastructure.bat / .ps1**
Sets up Docker network and Redis (one-time setup).

```batch
.\setup-infrastructure.bat
```

**What it does:**
- Creates `automation_network` (Docker network)
- Starts `automation_redis` container on port 6379
- Handles existing containers gracefully
- Provides next steps

---

### 2. **build-and-deploy.bat / .ps1**
Build and deploy individual services.

```batch
# Syntax
.\build-and-deploy.bat <role> <node_name> <command>

# Examples
.\build-and-deploy.bat orchestrator main serve      # API Server
.\build-and-deploy.bat worker w1 worker             # Worker
.\build-and-deploy.bat orchestrator main beat       # Scheduler
.\build-and-deploy.bat orchestrator main flower     # Monitoring
.\build-and-deploy.bat orchestrator main shell      # Django Shell
.\build-and-deploy.bat orchestrator main config     # Show Config
```

**Parameters:**
- `role`: `orchestrator` or `worker`
- `node_name`: `main`, `api`, `w1`, `w2`, etc.
- `command`: `serve`, `worker`, `beat`, `flower`, `shell`, `config`

**What it does:**
- Builds Docker image based on role
- Removes existing container (if any)
- Starts new container with proper networking
- Shows container info and logs command

---

### 2b. **build-and-deploy-ui.bat / .ps1** ⭐ NEW
Build and deploy React UI container separately.

```batch
# Syntax
.\build-and-deploy-ui.bat [command]

# Examples
.\build-and-deploy-ui.bat build               # Build image only
.\build-and-deploy-ui.bat run                 # Build and run container
.\build-and-deploy-ui.bat stop                # Stop running container
.\build-and-deploy-ui.bat start               # Start stopped container
.\build-and-deploy-ui.bat restart             # Restart container
.\build-and-deploy-ui.bat logs                # View container logs
.\build-and-deploy-ui.bat shell               # Open shell in container
.\build-and-deploy-ui.bat remove              # Remove container
.\build-and-deploy-ui.bat help                # Show help
```

**Commands:**
- `build` - Build React UI image only (default)
- `run` - Build and run UI container
- `stop` - Stop running UI container
- `start` - Start stopped UI container
- `restart` - Restart UI container
- `logs` - View container logs (real-time)
- `shell` - Open bash shell in running container
- `remove` - Remove UI container
- `help` - Show help message

**What it does:**
- Validates Docker and UI directory exist
- Builds multi-stage React Docker image
- Manages UI container lifecycle
- Provides useful shortcuts for common tasks

**Examples:**

```batch
REM Build only
.\build-and-deploy-ui.bat build

REM Build and run
.\build-and-deploy-ui.bat run

REM View logs in real-time
.\build-and-deploy-ui.bat logs

REM Restart container
.\build-and-deploy-ui.bat restart

REM Stop container (keep for later restart)
.\build-and-deploy-ui.bat stop

REM Start again
.\build-and-deploy-ui.bat start

REM PowerShell versions
.\build-and-deploy-ui.ps1 build
.\build-and-deploy-ui.ps1 run
.\build-and-deploy-ui.ps1 logs
```

---

### 3. **quick-start.bat / .ps1**
Start all services at once (infrastructure + API + worker + scheduler + UI + monitoring).

```batch
.\quick-start.bat
```

**What it does:**
1. Runs setup-infrastructure
2. Builds & starts Orchestrator (API)
3. Builds & starts Worker
4. Builds & starts Beat Scheduler
5. Builds & starts React UI
6. Builds & starts Flower Monitoring
7. Shows access URLs

**Result:** Full stack running after ~2-3 minutes

---

### 4. **stop-all.bat**
Stop all running automation containers (batch only) (keeps containers intact for restart).

```batch
.\stop-all.bat
```

**What it does:**
- Stops all containers named `automation*`
- Keeps containers available for restart
- Shows remaining status

---

### 5. **clean-all.bat**
Remove all automation containers, images, and network (batch only) (full cleanup).

```batch
.\clean-all.bat
```

⚠️ **WARNING:** This removes everything. Requires confirmation.

**What it does:**
- Stops all automation containers
- Removes all automation containers
- Removes all automation images
- Removes the automation network
- Resets to clean state

---

### 6. **status.bat / .ps1**
Show current status of all services.

```batch
.\status.bat
```

**Shows:**
- Docker availability
- Container status and ports
- Network status
- Redis connectivity
- Service URLs

---

### 7. **view-logs.bat / .ps1**
View real-time logs from containers.

```batch
# View specific container logs
.\view-logs.bat main       # Orchestrator API
.\view-logs.bat worker     # Celery Worker
.\view-logs.bat beat       # Beat Scheduler
.\view-logs.bat flower     # Flower UI
.\view-logs.bat ui         # React Frontend
.\view-logs.bat redis      # Redis

# View all containers status
.\view-logs.bat all

# View without arguments (shows help)
.\view-logs.bat
```

**Press Ctrl+C to stop viewing logs**

---

## 🚀 Quick Start Workflows

### Workflow 1: Complete Fresh Start
```batch
.\quick-start.bat
REM or manually:
.\setup-infrastructure.bat
.\build-and-deploy.bat orchestrator main serve
.\build-and-deploy.bat worker w1 worker
.\build-and-deploy.bat orchestrator main beat
.\build-and-deploy-ui.bat run
.\build-and-deploy.bat orchestrator main flower
```

### Workflow 2: Build and Deploy UI Only
```batch
.\build-and-deploy-ui.bat build              # Build image
.\build-and-deploy-ui.bat run                # Build and run
.\build-and-deploy-ui.bat logs               # View logs
.\build-and-deploy-ui.bat stop               # Stop container
.\build-and-deploy-ui.bat start              # Start again
```

### Workflow 3: Add More Workers
```batch
.\build-and-deploy.bat worker w2 worker
.\build-and-deploy.bat worker w3 worker
REM Scale as needed: w1, w2, w3, w4, etc.
```

### Workflow 4: Stop and Restart
```batch
.\stop-all.bat
REM Later, restart:
.\build-and-deploy.bat orchestrator main serve
.\build-and-deploy.bat worker w1 worker
.\build-and-deploy.bat orchestrator main beat
.\build-and-deploy-ui.bat start
.\build-and-deploy.bat orchestrator main flower
```

### Workflow 5: Full Reset
```batch
.\clean-all.bat
.\quick-start.bat
```

---

## 🔧 Quick Start

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

## 🛠️ Batch Script Troubleshooting

### Batch Scripts Won't Run
**Problem:** Scripts open in editor instead of executing
**Solution:** 
```powershell
# Right-click script and select "Run with PowerShell"
# Or open PowerShell and run:
cd C:\path\to\backend\automation
.\quick-start.bat
```

### "Docker is not installed or not in PATH"
**Solution:**
```powershell
# Ensure Docker is installed and added to PATH
# Restart PowerShell/CMD after installing Docker
docker --version
```

### Batch Script Fails to Find .env
**Problem:** `.env file not found` error
**Solution:**
```batch
# Ensure .env exists in backend/automation directory
cd backend/automation
type .env
REM or create from template:
copy .env.example .env
```

### Container Won't Start from Batch
**Problem:** Container starts but immediately stops
**Solution:**
```powershell
# Check logs
docker logs automation_main

# Verify .env file is valid
cat .env | findstr DB_

# Run with verbose output
docker run -it --env-file .env --network automation_network automation:orchestrator config
```

### Batch Script Freezes
**Problem:** Script hangs on a step
**Solution:**
```batch
# Press Ctrl+C to stop
# Check if service is running:
docker ps -a | findstr automation

# Try manually:
docker build --build-arg ROLE=orchestrator --build-arg IS_ORCHESTRATOR=True -t automation:orchestrator .
```

---

## 📋 Batch Script Reference

| Script | Purpose | Parameters |
|--------|---------|-----------|
| `setup-infrastructure.bat` | Setup network & Redis | None |
| `build-and-deploy.bat` | Build & run backend services | role, node_name, command |
| `build-and-deploy-ui.bat` ⭐ | Build & run React UI | command (build, run, stop, start, etc.) |
| `quick-start.bat` | Start everything | None |
| `stop-all.bat` | Stop all containers | None |
| `clean-all.bat` | Remove all (destructive) | None |
| `status.bat` | Show service status | None |
| `view-logs.bat` | View container logs | container_name |

---

## 🎯 Common Batch Script Commands

```batch
REM Show help for a script
.\build-and-deploy.bat

REM View all containers
.\status.bat

REM Backend & Infrastructure
REM ========================
REM Setup network and Redis
.\setup-infrastructure.bat

REM Build and deploy backend services
.\build-and-deploy.bat orchestrator main serve
.\build-and-deploy.bat worker w1 worker
.\build-and-deploy.bat orchestrator main beat
.\build-and-deploy.bat orchestrator main flower

REM React UI Commands
REM ==================
REM Build UI image only
.\build-and-deploy-ui.bat build

REM Build and run UI
.\build-and-deploy-ui.bat run

REM View UI logs in real-time
.\build-and-deploy-ui.bat logs

REM Stop UI container
.\build-and-deploy-ui.bat stop

REM Start UI container
.\build-and-deploy-ui.bat start

REM Restart UI container
.\build-and-deploy-ui.bat restart

REM Management Commands
REM ====================
REM View specific container logs in real-time
.\view-logs.bat main

REM Stop everything gracefully
.\stop-all.bat

REM Start fresh (full reset)
.\clean-all.bat
.\quick-start.bat

REM Add worker manually
.\build-and-deploy.bat worker w2 worker

REM Open Django shell
.\build-and-deploy.bat orchestrator main shell

REM Check configuration
.\build-and-deploy.bat orchestrator main config
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

---

## 📁 Script Directory Structure

```
backend/automation/
├── setup-infrastructure.bat      # Setup network & Redis
├── setup-infrastructure.sh       # Linux/Mac version
├── build-and-deploy.bat          # Build & run backend services
├── build-and-deploy.sh           # Linux/Mac version
├── build-and-deploy-ui.bat       # Build & run React UI ⭐ NEW
├── build-and-deploy-ui.ps1       # PowerShell UI version ⭐ NEW
├── quick-start.bat               # Start everything
├── quick-start.ps1               # PowerShell version
├── stop-all.bat                  # Stop all containers
├── clean-all.bat                 # Full cleanup
├── status.bat                    # Show status
├── status.ps1                    # PowerShell version
├── view-logs.bat                 # View container logs
├── view-logs.ps1                 # PowerShell version
├── Makefile                      # Alternative (Linux/Mac)
├── entrypoint.sh                 # Container entry point
├── nginx.conf                    # Nginx config for UI
└── Dockerfile                    # Backend Dockerfile
```

---

## 🚀 Recommended Setup for Windows Users

### First Time Setup

1. **Clone/Extract Project**
   ```powershell
   cd backend/automation
   ```

2. **Create .env File**
   ```powershell
   copy .env.example .env
   # Edit .env with your database credentials
   notepad .env
   ```

3. **Run Quick Start**
   ```powershell
   .\quick-start.bat
   # Or for colored output:
   .\quick-start.ps1
   ```

4. **Access Services**
   - Frontend: http://localhost:3000
   - API: http://localhost:8000
   - Flower: http://localhost:5555

### Daily Workflow

**Start services:**
```powershell
# Option 1: Quick start (all services)
.\quick-start.bat

# Option 2: Start individually
.\build-and-deploy.bat orchestrator main serve
.\build-and-deploy.bat worker w1 worker
.\build-and-deploy.bat orchestrator main beat
.\build-and-deploy-ui.bat run
.\build-and-deploy.bat orchestrator main flower

# Option 3: Start backend and UI separately
.\build-and-deploy.bat orchestrator main serve
.\build-and-deploy-ui.bat build    # Build only
.\build-and-deploy-ui.bat run      # Then run
```

**Check status:**
```powershell
.\status.bat
# or PowerShell version:
.\status.ps1
```

**View logs:**
```powershell
.\view-logs.bat main
.\view-logs.bat worker
.\view-logs.bat beat
.\view-logs.bat ui       # React frontend logs
```

**UI Management:**
```powershell
# Build only
.\build-and-deploy-ui.bat build

# Build and run
.\build-and-deploy-ui.bat run

# View logs
.\build-and-deploy-ui.bat logs

# Restart UI
.\build-and-deploy-ui.bat restart

# Stop UI (for updates/debugging)
.\build-and-deploy-ui.bat stop

# Start again
.\build-and-deploy-ui.bat start
```

**Stop services:**
```powershell
.\stop-all.bat
```

**Clean everything:**
```powershell
.\clean-all.bat
.\quick-start.bat
```

---

## ✅ Batch Script Features

✓ **Cross-platform**: Works on Windows CMD and PowerShell  
✓ **Error handling**: Checks for Docker, validates inputs  
✓ **Interactive**: Shows progress and helpful messages  
✓ **Safe**: Handles existing containers gracefully  
✓ **Informative**: Displays container status and URLs  
✓ **Logging**: Easy log viewing with view-logs script  
✓ **Cleanup**: Safe cleanup with confirmation prompts  
✓ **Flexible**: Run individual services or everything at once  
✓ **PowerShell Support**: Colorful output with .ps1 versions  
✓ **Auto-recovery**: Gracefully handles already-running services  
✓ **UI Management**: Dedicated script for React UI (build, run, stop, logs, shell, etc.)  
✓ **Modular**: Separate backend and UI build/deploy workflows  
✓ **Path Safety**: Proper path handling for Windows environments

---

## 🎓 Learning Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose](https://docs.docker.com/compose/)
- [Celery Documentation](https://docs.celeryproject.io/)
- [Django Deployment Guide](https://docs.djangoproject.com/en/stable/howto/deployment/)

