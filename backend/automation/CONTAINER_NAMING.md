# Container Naming Guide

## 🏷️ How Container Names Work Now

The script now creates smart container names that avoid conflicts:

### Naming Pattern

```
orchestrator main serve    → automation_main
orchestrator main beat     → automation_main_beat
orchestrator main flower   → automation_main_flower
worker w1 worker           → automation_w1_worker
worker w2 worker           → automation_w2_worker
```

## 📋 Command Suffix Rules

| Command | Suffix | Example |
|---------|--------|---------|
| `serve` | (none) | `automation_main` |
| `beat` | `_beat` | `automation_main_beat` |
| `flower` | `_flower` | `automation_main_flower` |
| `worker` | `_worker` | `automation_w1_worker` |
| `shell` | (none) | `automation_main` |
| `config` | (none) | `automation_main` |

## 🎯 Correct Usage Now

### API Server
```powershell
.\build-and-deploy.bat orchestrator main serve
# Creates: automation_main
```

### Scheduler (Beat)
```powershell
.\build-and-deploy.bat orchestrator main beat
# Creates: automation_main_beat (NOT automation_main)
```

### Workers
```powershell
.\build-and-deploy.bat worker w1 worker
# Creates: automation_w1_worker (NOT automation_w1)

.\build-and-deploy.bat worker w2 worker
# Creates: automation_w2_worker
```

### Monitoring (Flower)
```powershell
.\build-and-deploy.bat orchestrator main flower
# Creates: automation_main_flower (NOT automation_main)
```

## ✅ Fixed Issues

### ❌ Before (Conflicting Names)
```
orchestrator main serve   → automation_main ✓
orchestrator main beat    → automation_main ✗ CONFLICT!
orchestrator main flower  → automation_main ✗ CONFLICT!
```

### ✅ After (Unique Names)
```
orchestrator main serve   → automation_main
orchestrator main beat    → automation_main_beat
orchestrator main flower  → automation_main_flower
```

## 🔧 Now Run This

Since you already have `automation_main` running, you can now safely run:

```powershell
# Beat scheduler (will create automation_main_beat, not conflict)
.\build-and-deploy.bat orchestrator main beat

# Workers (will create automation_w1_worker, automation_w2_worker)
.\build-and-deploy.bat worker w1 worker
.\build-and-deploy.bat worker w2 worker

# Monitoring (will create automation_main_flower)
.\build-and-deploy.bat orchestrator main flower
```

## 🐳 View All Containers

```powershell
docker ps -a

# Should show all with UNIQUE names:
# automation_main (API)
# automation_main_beat (Scheduler)
# automation_w1_worker (Worker 1)
# automation_w2_worker (Worker 2)
# automation_main_flower (Flower UI)
# automation_redis (Redis Broker)
```

## 🗑️ If You Need to Rebuild

```powershell
# Remove old container
docker rm automation_main

# Rebuild
.\build-and-deploy.bat orchestrator main serve

# Or if you want to keep it running, just stop it
docker stop automation_main

# The beat can run along with it since they have different names now
.\build-and-deploy.bat orchestrator main beat
```

## ✨ Key Point

**The node name (`main`, `w1`, `w2`, etc.) stays the same.**  
**Only the command changes the container name suffix.**

So if you run:
```
.\build-and-deploy.bat orchestrator main serve    # container: automation_main
.\build-and-deploy.bat orchestrator main beat     # container: automation_main_beat
.\build-and-deploy.bat orchestrator main flower   # container: automation_main_flower
```

All three can run simultaneously without conflicts!
