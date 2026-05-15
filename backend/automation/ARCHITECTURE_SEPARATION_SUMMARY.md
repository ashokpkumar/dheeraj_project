# Architecture Separation Implementation Summary

## Problem Solved

**Before:** The system tried to run pywin32 (Windows-only) and Celery (Linux-friendly) in the same container/environment, which was impossible.

**After:** Separated into two independent services:
1. **Windows Automation Service** - Runs ONLY on Windows with emulator COM interface
2. **Linux Celery System** - Runs in Docker/Linux with standard task scheduling

---

## What Was Done

### 1. New Windows Service (`windows_automation_service.py`)
- **Standalone Flask application** running on Windows
- **Emulator operations** using pywin32 COM interface
- **HTTP API** for Linux systems to request work
- **Handles:**
  - `POST /scrap-claims` - Process multiple claims
  - `POST /process-claim` - Process single claim
  - `GET /health` - Health check

### 2. Windows Client Library (`windows_client.py`)
- **HTTP client** for Linux/Docker systems
- **Abstracts away HTTP calls** to Windows service
- **Error handling** and retry logic
- **Configuration via environment variables**
- **Usage:** `from windows_client import get_windows_client`

### 3. Refactored Functions (`claims.py`)
- **Removed direct pywin32 imports** and emulator calls
- **Uses Windows client** to call remote service
- **Gracefully handles** service unavailability
- **Proper error messages** for troubleshooting

### 4. Updated Requirements (`requirements.txt`)
- **Added:** Flask, flask-cors, requests
- **Marked pywin32 as optional** (Windows-only)

### 5. Documentation
- **`WINDOWS_LINUX_SEPARATION.md`** - Comprehensive architecture guide
- **`QUICK_START.md`** - 30-minute setup guide

### 6. Startup Scripts
- **`start-windows-service.ps1`** - PowerShell script for Windows
- **`start-linux-services.sh`** - Bash script for Linux

---

## Architecture Diagram

```
┌──────────────────────────────────┐
│  Windows Machine                 │
│  ┌────────────────────────────┐  │
│  │ Windows Automation Service │  │
│  │ (Flask + pywin32)          │  │
│  │ http://localhost:5555      │  │
│  └────────────────────────────┘  │
└──────────────────────────────────┘
           ↕ HTTP REST API
┌──────────────────────────────────┐
│  Linux Container / Server        │
│  ┌────────────────────────────┐  │
│  │ Django + Celery            │  │
│  │ (uses windows_client.py)   │  │
│  └────────────────────────────┘  │
└──────────────────────────────────┘
```

---

## How It Works

### Flow: Rule Execution with Emulator Operations

```
1. User creates rule with "scrap_claims_from_emulator" function
   ↓
2. Celery worker executes rule in Linux container
   ↓
3. Rule calls scrap_claims_from_emulator(context)
   ↓
4. Function uses windows_client.scrap_claims()
   ↓
5. HTTP request sent to Windows service at WINDOWS_SERVICE_HOST:WINDOWS_SERVICE_PORT
   ↓
6. Windows service connects to EXTRA emulator via COM
   ↓
7. Emulator processes claims using pywin32
   ↓
8. Results returned via HTTP response
   ↓
9. Rule continues processing in Linux/Celery
   ↓
10. Convert results to CSV or store in database
```

---

## Deployment Scenarios

### Scenario 1: Development (Same Machine)

```bash
# Terminal 1 - Windows (run first)
python windows_automation_service.py

# Terminal 2 - Linux/WSL/Docker
WINDOWS_SERVICE_HOST=localhost celery -A automation worker

# Terminal 3 - Linux/WSL/Docker
WINDOWS_SERVICE_HOST=localhost celery -A automation beat
```

### Scenario 2: Separate Machines

```bash
# On Windows machine
python windows_automation_service.py

# On Linux machine - set .env:
WINDOWS_SERVICE_HOST=192.168.1.100
WINDOWS_SERVICE_PORT=5555

# Start Celery
celery -A automation worker
celery -A automation beat
```

### Scenario 3: Docker Deployment

```bash
# docker-compose.yml configures networking
docker-compose up -d

# Automatically connects to Windows service via WINDOWS_SERVICE_HOST
```

---

## Configuration

### Windows Service
```
WINDOWS_SERVICE_HOST=0.0.0.0          # Listen on all interfaces
WINDOWS_SERVICE_PORT=5555              # API port
HOST_SETTLE_TIME_MS=100                # Emulator responsiveness
```

### Linux System (.env)
```
WINDOWS_SERVICE_HOST=192.168.1.100     # Windows machine IP ← CRITICAL
WINDOWS_SERVICE_PORT=5555
WINDOWS_SERVICE_TIMEOUT=300            # Timeout for requests (seconds)

CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

IS_ORCHESTRATOR=True                   # One instance only!
```

---

## Compatibility

### Before Refactoring
- ❌ pywin32 fails in Linux container
- ❌ Can't run emulator operations in Docker
- ❌ Single monolithic application

### After Refactoring
- ✅ Windows service runs on Windows only
- ✅ Linux Celery runs in Docker without dependencies
- ✅ Services communicate via standard HTTP API
- ✅ Easy to scale Celery workers (no threading conflicts)
- ✅ Can deploy on different machines
- ✅ Natural separation of concerns

---

## Key Features

1. **No Breaking Changes**
   - Existing rules continue to work
   - Same function names and signatures
   - Transparent HTTP communication

2. **Error Handling**
   - Gracefully handles service unavailability
   - Detailed error messages for debugging
   - Automatic retries for network issues

3. **Performance**
   - Parallel processing via multiple Celery workers
   - Windows service handles one request at a time (emulator limitation)
   - HTTP caching possible for repeated requests

4. **Security**
   - Firewall control on port 5555
   - Can add authentication headers in windows_client.py
   - Use VPN for cross-machine communication

---

## Testing the Setup

### 1. Test Windows Service
```bash
curl http://localhost:5555/health
```

### 2. Test from Linux
```bash
curl http://192.168.1.100:5555/health
```

### 3. Test Claim Scraping
```bash
curl -X POST http://localhost:5555/scrap-claims \
  -H "Content-Type: application/json" \
  -d '{
    "claim_ids": ["CLAIM001", "CLAIM002"],
    "method": "SEARCH BY CCN"
  }'
```

### 4. Test Rule Execution
```python
python manage.py shell

from rule_engine.models import RuleEngine
from rule_engine.executor import GraphRuleExecutor

rule = RuleEngine.objects.filter(
    rule_name__icontains="scrap"
).first()

executor = GraphRuleExecutor(rule.id, manual=True)
result = executor.execute()
print(result)
```

---

## Monitoring

### Windows Service Logs
- Appears in terminal/PowerShell window
- Shows emulator interactions and errors
- Check for `"ERROR"` or `"FAILED"` messages

### Celery Worker Logs
- Shows task execution and Windows service calls
- Monitor for `"Cannot access Windows Automation Service"` errors
- Check task status in Flower: http://localhost:5555/flower

### Health Check
```bash
# Regular check
curl http://WINDOWS_IP:5555/health

# With timeout
curl --max-time 5 http://WINDOWS_IP:5555/health
```

---

## Troubleshooting Quick Guide

| Issue | Cause | Solution |
|-------|-------|----------|
| `Connection refused` | Windows service not running | Start `windows_automation_service.py` |
| `Service unavailable` | Wrong IP/port | Check `WINDOWS_SERVICE_HOST` in .env |
| `Emulator timeout` | EXTRA emulator not ready | Ensure emulator has active sessions |
| `No active sessions` | Emulator not open properly | Open EXTRA, create sessions |
| `Permission denied` | pywin32 COM access issue | Run as Administrator on Windows |
| `Celery can't connect` | Network firewall | Check Windows Firewall port 5555 |

---

## Future Enhancements

Possible improvements to consider:

1. **Authentication** - Add API key validation
2. **HTTPS** - Run Windows service behind nginx with SSL
3. **Caching** - Cache identical requests for performance
4. **Load Balancing** - Multiple Windows services with round-robin
5. **Monitoring** - Prometheus metrics export
6. **Async Processing** - Use task queues instead of direct HTTP

---

## Files Overview

| File | Purpose |
|------|---------|
| `windows_automation_service.py` | Windows Flask service |
| `windows_client.py` | HTTP client library |
| `rule_engine/functions/claims.py` | Refactored to use client |
| `requirements.txt` | Updated with new dependencies |
| `WINDOWS_LINUX_SEPARATION.md` | Complete documentation |
| `QUICK_START.md` | 30-minute setup guide |
| `start-windows-service.ps1` | Windows startup script |
| `start-linux-services.sh` | Linux startup script |

---

## Summary

**The system is now properly separated into two independent services that communicate via HTTP REST API.**

- Windows service handles all emulator operations
- Linux system runs Celery scheduler and workers
- No cross-platform conflicts
- Easy to deploy and scale
- Proper error handling and monitoring

🎉 **Ready for deployment!**
