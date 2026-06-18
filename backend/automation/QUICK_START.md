# Quick Start: Separated Windows & Linux Architecture

## 30-Minute Setup Guide

### Prerequisites

✅ Done already:
- Windows and Linux machines networked together
- EXTRA emulator running on Windows machine

❌ Need to install:
- Python 3.8+ on Windows
- Python 3.8+ on Linux
- Redis on Linux (or Docker)
- Docker (optional, for Linux services)

---

## Step 1: Windows Service (5 minutes)

### 1.1 Install Dependencies on Windows

```powershell
# Open PowerShell as Administrator
pip install pywin32 flask flask-cors

# Post-install pywin32 (required for COM interface)
python -m pip install --force-reinstall --no-cache-dir pywin32
python Scripts/pywin32_postinstall.py -install
```

### 1.2 Start the Service

```powershell
cd c:\Users\ashok\Documents\dheeraj_project\dheeraj_project\backend\automation

# Make sure EXTRA emulator is running with sessions!

# Start the service
.\start-windows-service.ps1

# Output should show:
# Starting Windows Automation Service on 0.0.0.0:5555
# ⚠️  This service MUST run on Windows with EXTRA emulator open
```

✅ **Service is now running at `http://localhost:5555`**

Test it:
```powershell
curl http://localhost:5555/health
```

Should return: `{"status": "healthy", "service": "windows_automation"}`

---


cd ~/dheeraj_project/backend/automation

# Build images and start all services
docker compose up -d --build

# Verify all containers are running
docker compose ps

## Step 2: Linux/Celery Setup (10 minutes)

### 2.1 Install Dependencies on Linux

```bash
cd ~/dheeraj_project/backend/automation

# Install Python dependencies
pip install -r requirements.txt

# Install Redis (if not already running)
# Ubuntu/Debian:
sudo apt-get install redis-server
sudo systemctl start redis-server

# Or use Docker:
docker run -d -p 6379:6379 redis:7-alpine
```

### 2.2 Configure .env File

Create `.env` file in `automation/` directory:

```env
# Windows Service Connection (CRITICAL!)
WINDOWS_SERVICE_HOST=192.168.1.100        # ← Replace with YOUR Windows machine IP
WINDOWS_SERVICE_PORT=5555
WINDOWS_SERVICE_TIMEOUT=300

# Database (adjust as needed)
DB_ENGINE=django.db.backends.mssql
DB_HOST=localhost
DB_PORT=1433
DB_NAME=automation_db
DB_USER=sa
DB_PASSWORD=YourPassword

# Redis/Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Django
DEBUG=False
DJANGO_SETTINGS_MODULE=automation.settings
SECRET_KEY=your-secret-key-change-this-in-production

# Orchestrator mode (run ONE instance in production)
IS_ORCHESTRATOR=True
```

**⚠️ CRITICAL: Set `WINDOWS_SERVICE_HOST` to your Windows machine's IP address!**

To find Windows machine IP:
```powershell
# On Windows
ipconfig

# Look for "IPv4 Address" - something like 192.168.1.100
```

### 2.3 Run Migrations

```bash
python manage.py migrate
```

### 2.4 Test Windows Service Connection

```bash
# Make sure Windows service is still running!
# Then test from Linux:

curl http://192.168.1.100:5555/health

# Should return: {"status": "healthy", "service": "windows_automation"}
```

### 2.5 Start Celery Services

**Terminal 1 - Celery Worker:**
```bash
celery -A automation worker --loglevel=info
```

**Terminal 2 - Celery Beat (Scheduler):**
```bash
# Only run ONE instance!
celery -A automation beat --loglevel=info
```

**Terminal 3 - Django API (optional):**
```bash
python manage.py runserver 0.0.0.0:8000
```

---

## Step 3: Test the System (5 minutes)

### 3.1 From Django Admin

```bash
# Create a test rule or execute an existing rule
python manage.py shell

from rule_engine.models import RuleEngine
rule = RuleEngine.objects.first()

# Execute it - this should call Windows service
from rule_engine.executor import GraphRuleExecutor
executor = GraphRuleExecutor(rule.id, manual=True)
result = executor.execute()

print(result)  # Should show results from emulator
```

### 3.2 From Task Queue

```bash
# Submit a test task
from rule_engine.tasks import execute_rule_engine

result = execute_rule_engine.delay(rule_id=1, manual=True)
print(result.get())  # Wait for result
```

### 3.3 Check Logs

**Windows Service** - See output in Windows terminal
**Celery Worker** - See output in Linux terminal 1
**Celery Beat** - See output in Linux terminal 2

Look for messages like:
```
[2025-05-14 10:30:45] Requesting to scrap 5 claims from Windows service
[2025-05-14 10:30:50] Successfully scraped 5 claims
```

---

## Networking Troubleshooting

### ❌ "Connection refused" from Linux to Windows service

1. **Check Windows Service is Running**
   ```powershell
   netstat -ano | findstr :5555
   ```

2. **Check Windows IP is Correct**
   ```powershell
   ipconfig
   ```

3. **Check Firewall**
   ```powershell
   # Allow port 5555 in Windows Firewall
   New-NetFirewallRule -DisplayName "Windows Automation Service" -Direction Inbound -LocalPort 5555 -Protocol TCP -Action Allow
   ```

4. **Test from Linux**
   ```bash
   curl -v http://192.168.1.100:5555/health
   ```

### ❌ "Windows service unhealthy" from Celery

- Make sure EXTRA emulator is open on Windows
- Check Windows service logs (terminal where it's running)
- Verify WINDOWS_SERVICE_HOST is set correctly

### ❌ Emulator operations fail

- Verify EXTRA emulator has active sessions
- Check emulator is in correct screen state
- Review Windows service logs for details

---

## Production Deployment

### Docker Deployment (Recommended)

Save as `docker-compose.yml`:

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    
  celery-worker:
    build: .
    command: celery -A automation worker --loglevel=info
    environment:
      - WINDOWS_SERVICE_HOST=192.168.1.100  # ← Change this
      - WINDOWS_SERVICE_PORT=5555
      - CELERY_BROKER_URL=redis://redis:6379/0
      - DB_HOST=your-database-host
    depends_on:
      - redis
    
  celery-beat:
    build: .
    command: celery -A automation beat --loglevel=info
    environment:
      - WINDOWS_SERVICE_HOST=192.168.1.100  # ← Change this
      - CELERY_BROKER_URL=redis://redis:6379/0
      - DB_HOST=your-database-host
      - IS_ORCHESTRATOR=True
    depends_on:
      - redis
    
  api:
    build: .
    ports:
      - "8000:8000"
    command: gunicorn automation.wsgi:application --bind 0.0.0.0:8000
    environment:
      - WINDOWS_SERVICE_HOST=192.168.1.100  # ← Change this
      - CELERY_BROKER_URL=redis://redis:6379/0
      - DB_HOST=your-database-host
    depends_on:
      - redis
```

Start with:
```bash
docker-compose up -d
```

---

## Files Changed

✅ Created:
- `windows_automation_service.py` - Windows emulator service
- `windows_client.py` - Client library for calling service
- `start-windows-service.ps1` - Windows startup script
- `start-linux-services.sh` - Linux startup script
- `WINDOWS_LINUX_SEPARATION.md` - Full documentation

✅ Modified:
- `rule_engine/functions/claims.py` - Uses Windows client
- `requirements.txt` - Added Flask dependencies

---

## Next Steps

1. ✅ **Windows Setup** - Start `windows_automation_service.py`
2. ✅ **Linux Setup** - Start Celery worker and beat
3. ✅ **Test** - Execute a rule from Django admin
4. ✅ **Monitor** - Watch logs for any issues
5. ✅ **Deploy** - Use Docker for production

---

## Support

If you encounter issues:

1. **Check the logs** - Both Windows service and Celery workers
2. **Test connectivity** - `curl http://WINDOWS-IP:5555/health`
3. **Verify configuration** - `.env` file has correct WINDOWS_SERVICE_HOST
4. **Review documentation** - See `WINDOWS_LINUX_SEPARATION.md` for detailed info

Good luck! 🚀
