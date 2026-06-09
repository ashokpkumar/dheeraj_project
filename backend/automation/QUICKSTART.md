# Quick Start Guide

## 🚀 Getting Started with Docker & Celery

### Step 1: Prepare Environment

```bash
cd automation
cp .env.example .env
```

Edit `.env` and update these crucial settings:

```env
# Orchestrator mode (with scheduler)
IS_ORCHESTRATOR=True

# Database credentials
DB_HOST=your-mssql-server
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=your_password
DB_NAME=master

# Redis connection (Docker container name)
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

### Step 2: Build & Start

```bash
# Build Docker images (first time)
docker-compose build

# Start all services
docker-compose up -d

# Watch logs in real-time
docker-compose logs -f
```

### Step 3: Initialize Database

```bash
# Run migrations
docker-compose exec web python manage.py migrate

# Create admin user
docker-compose exec web python manage.py createsuperuser

# Check configuration
docker-compose exec web python manage.py show_config
```

### Step 4: Access Services

| Service | URL | Purpose |
|---------|-----|---------|
| Django Admin | http://localhost:8000/admin | Manage data |
| Flower | http://localhost:5555 | Monitor tasks |
| API | http://localhost:8000/api | REST endpoints |

## 🎯 Quick Commands

### View Logs
```bash
docker-compose logs -f web           # Django logs
docker-compose logs -f celery_worker # Worker logs
docker-compose logs -f celery_beat   # Scheduler logs
```

### Run Commands
```bash
docker-compose exec web python manage.py shell
docker-compose exec web python manage.py createsuperuser
docker-compose exec web python manage.py migrate
```

### Stop Services
```bash
docker-compose down              # Stop all services
docker-compose down -v           # Stop and remove volumes
docker-compose restart web       # Restart specific service
```

### Scale Workers
```bash
docker-compose up -d --scale celery_worker=3
```

## 📊 Monitoring

### Flower Dashboard
- Visit: http://localhost:5555
- Real-time task monitoring
- Worker status
- Task history

### Check Redis
```bash
docker-compose exec redis redis-cli
> ping
> keys *
> info
```

### View Active Tasks
```bash
docker-compose exec web python manage.py shell
>>> from celery.app.control import Inspect
>>> i = Inspect()
>>> i.active()
```

## 🔧 Configuration Modes

### Orchestrator Mode (Single Node)
```env
IS_ORCHESTRATOR=True
```
- Runs scheduler (Celery Beat)
- Executes tasks
- Manages jobs

### Worker Mode (Distributed)
```env
IS_ORCHESTRATOR=False
```
- Only executes tasks
- No scheduler
- Scale horizontally

## ⚠️ Important Notes

- **Only ONE Celery Beat scheduler** should run in production
- Use external Redis for production
- Update `SECRET_KEY` in Django settings
- Set `DEBUG=False` in production
- Run migrations before using
- Set proper database credentials

## 🐛 Troubleshooting

### Tasks not running?
```bash
docker-compose logs celery_worker | grep -i error
docker-compose exec redis redis-cli PING
```

### Scheduler not starting?
```bash
docker-compose logs celery_beat | grep -i "orchestrator\|scheduler"
```

### Connection errors?
```bash
docker-compose down -v
docker-compose up -d --build
```

## 📚 Full Documentation

See [DOCKER_README.md](DOCKER_README.md) for complete documentation.
