# Docker & Celery Setup Guide

This guide explains how to run the automation application using Docker with Celery, Redis, and Celery Beat for distributed task execution and scheduling.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Network                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │     Web      │  │   Worker     │  │    Beat      │      │
│  │  (Django)    │  │  (Celery)    │  │ (Scheduler)  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         │                 │                 │               │
│         └─────────────────┼─────────────────┘               │
│                           │                                 │
│                  ┌────────▼────────┐                        │
│                  │  Redis (Broker) │                        │
│                  └─────────────────┘                        │
│                           │                                 │
│                  ┌────────▼────────┐                        │
│                  │  Flower (UI)    │ :5555                  │
│                  └─────────────────┘                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. **Web (Django Application)**
   - Handles HTTP requests
   - Exposes REST API
   - Delegates long-running tasks to Celery workers
   - Port: 8000

### 2. **Celery Worker**
   - Executes rule engine tasks
   - Processes queued jobs from Redis
   - Can scale horizontally by running multiple instances

### 3. **Celery Beat (Scheduler)**
   - Runs only in **ORCHESTRATOR mode**
   - Periodically syncs scheduled jobs from database
   - Triggers rule engine executions based on schedule
   - Only ONE instance should run in orchestrator mode

### 4. **Redis**
   - Message broker for Celery
   - Stores task results
   - Port: 6379

### 5. **Flower**
   - Celery monitoring and management UI
   - Real-time task monitoring
   - Port: 5555
   - URL: http://localhost:5555

## Setup Instructions

### Prerequisites
- Docker
- Docker Compose
- MS SQL Server (local or external)
- At least 4GB RAM available

### 1. Update Environment Variables

Copy and update the `.env.example` file:
```bash
cp .env.example .env
```

Edit `.env` and set:
```env
# For Orchestrator Instance (with scheduler)
IS_ORCHESTRATOR=True

# For Worker Instance (without scheduler)
IS_ORCHESTRATOR=False

# Database settings
DB_HOST=your_mssql_host
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=your_password
```

### 2. Build Docker Images

```bash
docker-compose build
```

### 3. Run the Stack

#### Option A: Full Stack (Recommended for Development)
```bash
docker-compose up -d
```

This starts:
- Django web application (port 8000)
- Celery worker
- Celery Beat scheduler (in orchestrator mode)
- Redis
- Flower (port 5555)

#### Option B: Without Scheduler (Worker-Only)
Edit `docker-compose.yml` and set `IS_ORCHESTRATOR=False` in celery_beat service, then:
```bash
docker-compose up -d
```

### 4. Initialize Database

Run migrations (if needed):
```bash
docker-compose exec web python manage.py migrate
```

Create superuser:
```bash
docker-compose exec web python manage.py createsuperuser
```

### 5. Access Services

- **Django Admin**: http://localhost:8000/admin
- **Flower (Celery UI)**: http://localhost:5555
- **Redis**: localhost:6379

## Configuration Modes

### Orchestrator Mode (`IS_ORCHESTRATOR=True`)

In this mode, the instance:
- ✅ Runs Celery Beat scheduler
- ✅ Syncs scheduled jobs every 5 minutes
- ✅ Can execute tasks directly (fallback)
- ✅ Manages job lifecycle
- ⚠️ **Only ONE orchestrator should run in production**

Use for:
- Single-node setups
- Development environments
- Primary production node

### Worker Mode (`IS_ORCHESTRATOR=False`)

In this mode, the instance:
- ❌ Does NOT run Celery Beat
- ✅ Only executes tasks from queue
- ✅ Can be scaled horizontally
- ✅ Pure task execution

Use for:
- Distributed setups
- Additional worker nodes
- High-throughput scenarios

## Scaling the System

### Add More Workers

```bash
docker-compose up -d --scale celery_worker=3
```

Creates 3 worker instances sharing the workload.

### Multi-Node Orchestrator Setup

**Node 1 (Orchestrator + Worker):**
```env
IS_ORCHESTRATOR=True
```

**Nodes 2-N (Workers Only):**
```env
IS_ORCHESTRATOR=False
```

All nodes connect to the same Redis broker and database.

## Monitoring & Management

### Flower Dashboard

Access http://localhost:5555 to:
- Monitor active tasks
- View task history
- Inspect worker status
- Manage task routing
- View task results

### View Logs

```bash
# Web logs
docker-compose logs -f web

# Worker logs
docker-compose logs -f celery_worker

# Scheduler logs
docker-compose logs -f celery_beat

# Flower logs
docker-compose logs -f flower
```

### Execute Commands

```bash
# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Run shell
docker-compose exec web python manage.py shell

# Run tests
docker-compose exec web python manage.py test
```

### Manual Task Execution

From Django shell:
```python
from rule_engine.tasks import execute_rule_engine

# Trigger immediate execution
task = execute_rule_engine.delay(rule_engine_id=1, manual=False)
print(task.id)  # Get task ID

# Check status
from celery.result import AsyncResult
result = AsyncResult(task_id)
print(result.status)
print(result.result)
```

## Task Scheduling

Scheduled jobs are managed through the Django admin or model:

```python
from rule_engine.models import ScheduledJob

job = ScheduledJob.objects.create(
    rule_name="my_rule",
    rule_id=1,
    is_active=True,
    schedule_config={
        "type": "daily",
        "time": "08:00"
    }
)
```

Supported schedule types:
- **interval**: Run every N seconds/minutes/hours
- **daily**: Run at specific time each day
- **weekly**: Run on specific days at specific time
- **once**: One-time execution

## Production Checklist

- [ ] Use environment variables for all secrets
- [ ] Update Django `SECRET_KEY` in `.env`
- [ ] Set `DEBUG=False` in production
- [ ] Configure proper Redis persistence
- [ ] Use external Redis for redundancy
- [ ] Run only ONE Celery Beat instance
- [ ] Scale workers based on load
- [ ] Monitor Flower for issues
- [ ] Set up log aggregation
- [ ] Configure proper error handling
- [ ] Use separate database for production
- [ ] Setup Redis password authentication
- [ ] Configure CORS properly
- [ ] Use SSL/TLS for connections

## Troubleshooting

### Tasks Not Executing

```bash
# Check Celery worker
docker-compose logs celery_worker

# Verify Redis connection
docker-compose exec redis redis-cli ping

# Check Flower for errors
# Visit http://localhost:5555
```

### Redis Connection Error

```bash
# Verify Redis is running
docker-compose ps

# Test Redis connection
docker-compose exec redis redis-cli

# Restart Redis
docker-compose restart redis
```

### Database Connection Error

```bash
# Verify database configuration in .env
docker-compose logs web

# Test database connection
docker-compose exec web python manage.py dbshell
```

### Scheduler Not Running

```bash
# Check if orchestrator mode is enabled
docker-compose logs celery_beat | grep "IS_ORCHESTRATOR"

# Verify Beat process is running
docker-compose ps celery_beat
```

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | False | Django debug mode |
| `IS_ORCHESTRATOR` | True | Enable scheduler |
| `CELERY_BROKER_URL` | redis://redis:6379/0 | Redis broker URL |
| `CELERY_RESULT_BACKEND` | redis://redis:6379/0 | Redis result backend |
| `DB_ENGINE` | mssql | Database engine |
| `DB_HOST` | localhost | Database host |
| `DB_PORT` | 1433 | Database port |
| `DB_USER` | sa | Database user |
| `DB_PASSWORD` | - | Database password |
| `DB_NAME` | master | Database name |

## Additional Resources

- [Celery Documentation](https://docs.celeryproject.io/)
- [Docker Documentation](https://docs.docker.com/)
- [Redis Documentation](https://redis.io/documentation)
- [Flower Documentation](https://flower.readthedocs.io/)
- [Django Celery Integration](https://docs.celeryproject.io/en/stable/django/)
