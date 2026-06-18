import os
from celery import Celery
from celery.schedules import crontab
from django.conf import settings

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'automation.settings')

app = Celery('automation')

# Load configuration from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all registered Django apps
app.autodiscover_tasks()

# Celery Beat Schedule Configuration for Orchestrator Mode
if settings.IS_ORCHESTRATOR:
    app.conf.beat_schedule = {
        'sync-scheduled-jobs': {
            'task': 'rule_engine.tasks.sync_scheduled_jobs',
            'schedule': crontab(minute='*/5'),  # Run every 5 minutes
        },
    }
else:
    # Worker mode: no scheduler tasks
    app.conf.beat_schedule = {}


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
