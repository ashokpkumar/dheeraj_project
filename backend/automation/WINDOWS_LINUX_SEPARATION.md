# Separated Architecture: Windows Automation Service & Linux Celery

## Overview

This guide explains how to run the pywin32-based Windows automation separate from the Linux-compatible Celery scheduler. This solves the cross-platform incompatibility issue where:

- **pywin32** requires Windows and cannot run in Linux containers
- **Celery** is best deployed in Linux containers but doesn't need Windows dependencies
- **Solution**: Two independent services that communicate via HTTP API

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Windows Machine                                             │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Windows Automation Service (Flask)                    │  │
│  │  - Emulator COM interface (pywin32)                    │  │
│  │  - HTTP API on localhost:5555                          │  │
│  │  - Requires EXTRA emulator running                     │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                            ↕ HTTP
┌──────────────────────────────────────────────────────────────┐
│  Linux Container / Linux Machine                             │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Django + Celery (celery worker / celery beat)         │  │
│  │  - Rule engine scheduler                               │  │
│  │  - Task execution                                      │  │
│  │  - Calls Windows service when emulator needed          │  │
│  │  - No Windows dependencies                             │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## Part 1: Windows Automation Service

### Requirements

- **Windows 10/11 or Windows Server 2019+**
- **Python 3.8+**
- **EXTRA Emulator** running with sessions open
- **pywin32** (for COM interface)
- **Flask** (for HTTP API)

### Setup

1. **Install dependencies**:
```bash
pip install pywin32 flask flask-cors requests
```

2. **Run Windows service**:
```bash
python windows_automation_service.py
```

Output:
```
Starting Windows Automation Service on 0.0.0.0:5555
⚠️  This service MUST run on Windows with EXTRA emulator open
```

### Environment Variables

Configure the Windows service with:
```
WINDOWS_SERVICE_HOST=0.0.0.0          # Listen on all interfaces
WINDOWS_SERVICE_PORT=5555              # HTTP API port
HOST_SETTLE_TIME_MS=100                # Emulator wait time (ms)
```

### API Endpoints

#### Health Check
```bash
GET /health
```
Response:
```json
{"status": "healthy", "service": "windows_automation"}
```

#### Scrap Multiple Claims
```bash
POST /scrap-claims
Content-Type: application/json

{
  "claim_ids": ["claim1", "claim2", ...],
  "method": "SEARCH BY CCN",
  "cert_date_mmddyy": "010120",
  "seq_no": "00",
  "dental_flag": false
}
```
Response:
```json
{
  "status": "success",
  "count": 2,
  "results": [
    {
      "CLAIM CONTROL #": "claim1",
      "MACRO STATUS": "DONE.",
      ...
    },
    ...
  ]
}
```

#### Process Single Claim
```bash
POST /process-claim
Content-Type: application/json

{
  "claim_id": "claim1",
  "method": "SEARCH BY CCN",
  "cert_date_mmddyy": "010120",
  "seq_no": "00",
  "dental_flag": false
}
```

### Running as Windows Service (Optional)

For production, you can register the service to run automatically:

```bash
# Install as Windows service
python -m pip install pywin32 --force-reinstall --no-cache-dir
python Scripts/pywin32_postinstall.py -install

# Create Windows service
sc create "WindowsAutomationService" binPath= "C:\path\to\python.exe C:\path\to\windows_automation_service.py"

# Start service
sc start WindowsAutomationService
```

## Part 2: Linux Celery System

### Requirements

- **Linux / Docker**
- **Python 3.8+**
- **Redis** (for Celery broker)
- **PostgreSQL/MSSQL** (for database)

### Setup

1. **Install dependencies**:
```bash
pip install -r requirements.txt
# Already includes: celery, redis, requests, windows-client module
```

2. **Environment Configuration**

Create `.env` file in the automation directory:
```env
# Django
DEBUG=False
DJANGO_SETTINGS_MODULE=automation.settings
SECRET_KEY=your-secret-key-here

# Database
DB_ENGINE=django.db.backends.mssql
DB_HOST=localhost
DB_PORT=1433
DB_NAME=automation_db
DB_USER=sa
DB_PASSWORD=password

# Redis/Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CELERY_TASK_TIME_LIMIT=1800

# Windows Service Connection
WINDOWS_SERVICE_HOST=192.168.1.100        # IP of Windows machine
WINDOWS_SERVICE_PORT=5555
WINDOWS_SERVICE_TIMEOUT=300               # 5 minutes for long operations

# Orchestrator mode (only one instance in production)
IS_ORCHESTRATOR=True
```

3. **Run Celery Worker**:
```bash
celery -A automation worker --loglevel=info
```

4. **Run Celery Beat (Scheduler)** - Only one instance:
```bash
celery -A automation beat --loglevel=info
```

Or combined:
```bash
celery -A automation worker --beat --loglevel=info
```

### Docker Deployment

#### Dockerfile for Linux Service

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run migrations
RUN python manage.py migrate

# Default: Run Celery worker
CMD ["celery", "-A", "automation", "worker", "--loglevel=info"]
```

#### Docker Compose Example

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  database:
    image: mcr.microsoft.com/mssql/server:2019-latest
    environment:
      SA_PASSWORD: "YourStrong!Password"
      ACCEPT_EULA: "Y"
    ports:
      - "1433:1433"

  celery-worker:
    build: .
    command: celery -A automation worker --loglevel=info
    environment:
      - WINDOWS_SERVICE_HOST=host.docker.internal  # On Docker Desktop
      # OR use actual Windows machine IP:
      # - WINDOWS_SERVICE_HOST=192.168.1.100
      - WINDOWS_SERVICE_PORT=5555
      - CELERY_BROKER_URL=redis://redis:6379/0
      - DB_HOST=database
    depends_on:
      - redis
      - database

  celery-beat:
    build: .
    command: celery -A automation beat --loglevel=info
    environment:
      - WINDOWS_SERVICE_HOST=host.docker.internal
      - WINDOWS_SERVICE_PORT=5555
      - CELERY_BROKER_URL=redis://redis:6379/0
      - DB_HOST=database
      - IS_ORCHESTRATOR=True
    depends_on:
      - redis
      - database

  api:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    ports:
      - "8000:8000"
    environment:
      - WINDOWS_SERVICE_HOST=host.docker.internal
      - WINDOWS_SERVICE_PORT=5555
      - CELERY_BROKER_URL=redis://redis:6379/0
      - DB_HOST=database
    depends_on:
      - redis
      - database
```

## Part 3: Cross-Platform Communication

### Windows Service Client (windows_client.py)

This client is used in the Linux/Celery system to call the Windows service:

```python
from windows_client import get_windows_client

# Get configured client
client = get_windows_client()

# Check if service is available
if client.health_check():
    print("Windows service is available")

# Scrap claims
results = client.scrap_claims(
    claim_ids=['claim1', 'claim2'],
    method='SEARCH BY CCN',
    cert_date_mmddyy='010120'
)

print(f"Scraped {len(results)} claims")
```

### Rule Engine Integration

In your rule workflows, the `scrap_claims_from_emulator` function now transparently calls the Windows service:

```python
# In a rule definition
{
    "steps": [
        {
            "function": "scrap_claims_from_emulator",
            "inputs": {
                "claim_ids": ["claim1", "claim2"],
                "method": "SEARCH BY CCN"
            },
            "outputs": {
                "scrapped_claims": "claims_data"
            }
        },
        {
            "function": "convert_claims_data_to_csv",
            "inputs": {
                "output_path": "/tmp/claims.csv",
                "scrapped_claims": "claims_data"
            },
            "outputs": {
                "status": "conversion_status"
            }
        }
    ]
}
```

## Part 4: Networking Considerations

### Local Development

- Windows service and Linux system on same machine: Use `localhost` or `127.0.0.1`
- Set `WINDOWS_SERVICE_HOST=localhost` in .env

### Docker on Windows (Docker Desktop)

- Use `host.docker.internal` to access Windows host from container
- Set `WINDOWS_SERVICE_HOST=host.docker.internal` in docker-compose.yml

### Separate Windows & Linux Machines

- Windows service accessible at: `http://<windows-ip>:5555`
- Set `WINDOWS_SERVICE_HOST=<windows-ip>` in .env
- Ensure firewall allows port 5555 traffic

### Network Security

For production:
1. **Use VPN or private network** - Don't expose port 5555 on public internet
2. **Add authentication** - Extend windows_client.py with API key validation
3. **Use HTTPS** - Run behind nginx/Apache with SSL
4. **Rate limiting** - Add rate limiting to prevent abuse

## Troubleshooting

### Windows Service Won't Start

```bash
# Check if port 5555 is in use
netstat -ano | findstr :5555

# Check if EXTRA emulator is running
tasklist | findstr EXTRA

# Run with debug output
python windows_automation_service.py
```

### Celery Can't Connect to Windows Service

```bash
# From Linux container, test connectivity
curl http://<windows-ip>:5555/health

# Check environment variables
echo $WINDOWS_SERVICE_HOST
echo $WINDOWS_SERVICE_PORT

# Review logs
docker logs <celery-container-id>
```

### Emulator Operations Fail

```bash
# Verify EXTRA emulator is open with sessions
# Check Windows service logs for detailed error messages
# Ensure emulator is in correct screen state
```

## Deployment Checklist

- [ ] Windows service running on Windows machine with EXTRA emulator open
- [ ] Windows service port (5555) accessible from Linux system
- [ ] Redis running and accessible
- [ ] Database running and accessible
- [ ] Celery worker started
- [ ] Celery beat scheduler started (one instance only)
- [ ] WINDOWS_SERVICE_HOST configured correctly
- [ ] Health check passes: `curl http://<windows-ip>:5555/health`
- [ ] Test rule execution from Django admin
- [ ] Monitor logs for errors

## Files Modified

- `windows_automation_service.py` - New standalone Windows service
- `windows_client.py` - New HTTP client for Celery system
- `rule_engine/functions/claims.py` - Refactored to use client
- `.env` - Add Windows service configuration

## Next Steps

1. Start Windows service on Windows machine
2. Configure WINDOWS_SERVICE_HOST in .env
3. Start Celery worker and beat in Linux
4. Test with a simple rule execution
5. Monitor logs and adjust as needed
