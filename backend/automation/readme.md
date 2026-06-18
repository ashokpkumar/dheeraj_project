# Automation Rule Engine

A Django-based rule engine with Celery for distributed task execution and scheduling.

## Features

✅ Rule engine with graph-based execution  
✅ Scheduled job execution with Celery Beat  
✅ Distributed task processing with Celery workers  
✅ Redis as message broker  
✅ Celery monitoring UI (Flower)  
✅ Docker & docker-compose support  
✅ Configurable orchestrator/worker mode  
✅ Multi-node scalability  

## Quick Start

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DJANGO_SETTINGS_MODULE=automation.settings
export IS_ORCHESTRATOR=True

# Run migrations
python manage.py migrate

# Start development server
python manage.py runserver
```

### Docker Setup
```bash
# Copy environment template
cp .env.example .env

# Build and start
docker-compose build
docker-compose up -d

# Access services
# - Django: http://localhost:8000
# - Flower: http://localhost:5555
```

See [QUICKSTART.md](QUICKSTART.md) for detailed setup instructions.  
See [DOCKER_README.md](DOCKER_README.md) for complete documentation.

## Project Structure

```
automation/
├── automation/          # Django project config
│   ├── settings.py     # Django settings (includes Celery config)
│   ├── celery.py       # Celery app configuration
│   └── urls.py         # URL routing
├── rule_engine/        # Rule engine app
│   ├── models.py       # Database models
│   ├── executor.py     # Rule execution logic
│   ├── tasks.py        # Celery tasks
│   ├── views.py        # API views
│   └── management/     # Django commands
├── manage.py           # Django CLI
├── requirements.txt    # Python dependencies
├── Dockerfile          # Docker image
├── docker-compose.yml  # Multi-container setup
└── DOCKER_README.md    # Docker documentation
```

## Configuration

Set environment variables to configure the application:

```env
IS_ORCHESTRATOR=True|False      # Enable scheduler
CELERY_BROKER_URL=redis://...   # Redis broker
DEBUG=True|False                # Django debug mode
DB_HOST=localhost               # Database host
DB_PORT=1433                    # Database port
DB_USER=sa                      # Database user
DB_PASSWORD=password            # Database password
```

## Running Modes

### Orchestrator Mode (`IS_ORCHESTRATOR=True`)
- Runs Celery Beat scheduler
- Manages scheduled jobs
- Executes tasks
- **Run only ONE instance in production**

### Worker Mode (`IS_ORCHESTRATOR=False`)
- Only executes tasks
- No scheduler
- Scale horizontally

## API Documentation

### Execute Rule Engine
```bash
POST /api/rule-engines/{id}/execute/
Content-Type: application/json

Response:
{
  "status": "success",
  "rule_engine_id": 1,
  "execution_log": [...]
}
```

### List Scheduled Jobs
```bash
GET /api/scheduled-jobs/
```

### Create Scheduled Job
```bash
POST /api/scheduled-jobs/
Content-Type: application/json

{
  "rule_name": "daily_audit",
  "rule_id": 1,
  "is_active": true,
  "schedule_config": {
    "type": "daily",
    "time": "08:00"
  }
}
```

## Monitoring

### Flower (Celery UI)
Access http://localhost:5555 for:
- Task monitoring
- Worker status
- Task history
- System statistics

### Logs
```bash
docker-compose logs -f web           # Django
docker-compose logs -f celery_worker # Worker
docker-compose logs -f celery_beat   # Scheduler
```

## Troubleshooting

See [DOCKER_README.md](DOCKER_README.md) for detailed troubleshooting guide.

## Production Deployment

1. Update environment variables
2. Use external Redis and database
3. Run only ONE Celery Beat instance
4. Scale workers based on load
5. Monitor with Flower
6. Enable error logging and alerts