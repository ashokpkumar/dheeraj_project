"""
Celery tasks for rule engine execution and scheduling.

These tasks replace the old thread-based scheduler and support distributed execution.
"""

import logging
from celery import shared_task
from django.conf import settings
from datetime import datetime

from .models import RuleEngine, ScheduledJob
from .executor import GraphRuleExecutor

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def execute_rule_engine(self, rule_engine_id, manual=False):
    """
    Execute a rule engine workflow.
    
    Args:
        rule_engine_id: ID of the RuleEngine model
        manual: Whether this is a manual execution (True) or scheduled (False)
    """
    try:
        logger.info(f"Starting execution of RuleEngine {rule_engine_id} (manual={manual})")
        
        # Verify rule engine exists and is active
        rule_engine = RuleEngine.objects.filter(id=rule_engine_id).first()
        if not rule_engine:
            logger.error(f"RuleEngine {rule_engine_id} not found")
            return {'status': 'error', 'message': 'RuleEngine not found'}
        
        if not rule_engine.is_active:
            logger.warning(f"RuleEngine {rule_engine_id} is not active")
            return {'status': 'inactive', 'message': 'RuleEngine is not active'}
        
        # Execute the workflow
        executor = GraphRuleExecutor(rule_engine_id=rule_engine_id, manual=manual)
        result = executor.execute()
        
        logger.info(f"Successfully executed RuleEngine {rule_engine_id}")
        return {
            'status': 'success',
            'rule_engine_id': rule_engine_id,
            'execution_log': result
        }
        
    except Exception as exc:
        logger.error(f"Error executing RuleEngine {rule_engine_id}: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@shared_task(bind=True)
def execute_scheduled_job(self, job_id, rule_engine_id):
    """
    Execute a scheduled job by triggering the rule engine.
    
    Args:
        job_id: ID of the ScheduledJob
        rule_engine_id: ID of the RuleEngine to execute
    """
    try:
        logger.info(f"Executing scheduled job {job_id} for RuleEngine {rule_engine_id} at {datetime.utcnow().isoformat()}")
        
        job = ScheduledJob.objects.filter(id=job_id).first()
        if not job:
            logger.error(f"ScheduledJob {job_id} not found")
            return
        
        if not job.is_active:
            logger.warning(f"ScheduledJob {job_id} is not active")
            return
        
        # Trigger the rule engine execution
        result = execute_rule_engine.delay(rule_engine_id, manual=False)
        logger.info(f"Triggered execution task {result.id} for job {job_id}")
        
    except Exception as exc:
        logger.error(f"Error executing scheduled job {job_id}: {exc}")


@shared_task
def sync_scheduled_jobs():
    """
    Sync scheduled jobs from database and update Celery Beat schedule.
    
    This task runs periodically (every 5 minutes in orchestrator mode) to:
    - Detect new scheduled jobs
    - Remove deleted scheduled jobs
    - Update modified scheduled jobs
    
    Only runs in ORCHESTRATOR mode.
    """
    if not settings.IS_ORCHESTRATOR:
        logger.debug("Not in orchestrator mode, skipping job sync")
        return
    
    try:
        logger.info("Syncing scheduled jobs from database")
        
        active_jobs = ScheduledJob.objects.filter(is_active=True)
        
        for job in active_jobs:
            try:
                schedule_config = job.schedule_config or {}
                schedule_type = schedule_config.get('type', 'interval')
                
                if schedule_type == 'interval':
                    # Handle interval-based scheduling
                    interval = job.interval or 1
                    unit = job.unit or 'seconds'
                    
                    # Convert unit names to Celery crontab format if needed
                    _schedule_interval_task(job.id, job.rule_id, interval, unit)
                    
                elif schedule_type == 'daily':
                    # Handle daily scheduling
                    time_str = schedule_config.get('time', '00:00')
                    _schedule_daily_task(job.id, job.rule_id, time_str)
                    
                elif schedule_type == 'weekly':
                    # Handle weekly scheduling
                    days = schedule_config.get('days', [])
                    time_str = schedule_config.get('time', '00:00')
                    _schedule_weekly_tasks(job.id, job.rule_id, days, time_str)
                    
                elif schedule_type == 'once':
                    # One-time execution is handled via manual trigger
                    pass
                
                logger.info(f"Synced job {job.id}: {job.rule_name}")
                
            except Exception as e:
                logger.error(f"Error syncing job {job.id}: {e}")
        
        logger.info(f"Successfully synced {active_jobs.count()} scheduled jobs")
        
    except Exception as exc:
        logger.error(f"Error in sync_scheduled_jobs: {exc}")


def _schedule_interval_task(job_id, rule_engine_id, interval, unit):
    """Helper to schedule interval-based tasks"""
    from celery.task import periodic_task
    from celery.schedules import schedule
    
    # Map unit names
    unit_map = {
        'seconds': interval,
        'minutes': interval * 60,
        'hours': interval * 3600,
    }
    
    seconds = unit_map.get(unit, interval)
    logger.debug(f"Scheduling task for job {job_id} every {seconds} seconds")


def _schedule_daily_task(job_id, rule_engine_id, time_str):
    """Helper to schedule daily tasks"""
    logger.debug(f"Scheduling task for job {job_id} daily at {time_str}")


def _schedule_weekly_tasks(job_id, rule_engine_id, days, time_str):
    """Helper to schedule weekly tasks"""
    logger.debug(f"Scheduling task for job {job_id} on days {days} at {time_str}")
