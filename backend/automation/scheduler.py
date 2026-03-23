# myproject/scheduler.py
import django
import os
import schedule
import time
import logging

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'automation.settings')
django.setup()

from rule_engine.models import RuleEngine
from rule_engine.executor import GraphRuleExecutor as RuleExecutor
from rule_engine.models import ScheduledJob   # ← your new model

logger = logging.getLogger(__name__)

# ── Tracks registered jobs: { ScheduledJob.id -> (schedule.Job, interval, unit) }
_registered_jobs: dict = {}


def _make_task(rule_name: str):
    """
    Returns a plain callable that runs the named RuleEngine rule.
    Using a factory keeps the closure correct for each iteration.
    """
    def task():
        try:
            print(f"[scheduler] Running rule: {rule_name}")
            rule_obj = RuleEngine.objects.filter(rule_name=rule_name).first()
            if not rule_obj:
                logger.warning(f"[scheduler] RuleEngine '{rule_name}' not found — skipping")
                return
            executor = RuleExecutor(rule_obj.id)
            executor.execute()
        except Exception as e:
            logger.error(f"[scheduler] Error running '{rule_name}': {e}")

    task.__name__ = f"task_{rule_name}"
    return task


def _build_schedule_job(db_job: "ScheduledJob") -> schedule.Job:
    """Register a single ScheduledJob with the schedule library and return it."""
    every = schedule.every(db_job.interval)

    unit_map = {
        "seconds": every.seconds,
        "minutes": every.minutes,
        "hours":   every.hours,
    }

    scheduled = unit_map.get(db_job.unit, every.seconds)
    return scheduled.do(_make_task(db_job.rule_name))


def sync_jobs_from_db():
    """
    Diff the DB against currently registered jobs:
      - New active jobs      → register
      - Deactivated/deleted  → cancel
      - Changed interval/unit → cancel + re-register
    Called once at startup and then every 60 seconds.
    """
    db_jobs = {job.id: job for job in ScheduledJob.objects.all()}

    # ── Cancel jobs that were removed or deactivated ──────────────────────
    for job_id in list(_registered_jobs.keys()):
        db_job = db_jobs.get(job_id)
        if db_job is None or not db_job.is_active:
            sched_job, _, __ = _registered_jobs.pop(job_id)
            schedule.cancel_job(sched_job)
            label = db_job.rule_name if db_job else job_id
            print(f"[scheduler] Cancelled job: {label}")

    # ── Register new active jobs / re-register changed ones ───────────────
    for job_id, db_job in db_jobs.items():
        if not db_job.is_active:
            continue

        existing = _registered_jobs.get(job_id)

        if existing is not None:
            sched_job, reg_interval, reg_unit = existing
            # Check if interval or unit changed → cancel and re-register
            if reg_interval == db_job.interval and reg_unit == db_job.unit:
                continue  # nothing changed
            schedule.cancel_job(sched_job)
            del _registered_jobs[job_id]
            print(f"[scheduler] Re-registering changed job: {db_job.rule_name}")

        sched_job = _build_schedule_job(db_job)
        _registered_jobs[job_id] = (sched_job, db_job.interval, db_job.unit)
        print(f"[scheduler] Registered: {db_job.rule_name} — every {db_job.interval} {db_job.unit}")


# ── Startup ───────────────────────────────────────────────────────────────────
print("[scheduler] Starting dynamic scheduler...")
sync_jobs_from_db()

# Re-sync DB every 60 seconds so new/changed/removed jobs take effect live
schedule.every(60).seconds.do(sync_jobs_from_db)

print("[scheduler] Scheduler running")
while True:
    schedule.run_pending()
    time.sleep(1)
