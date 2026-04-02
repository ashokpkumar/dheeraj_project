# myproject/scheduler.py
import django
import os
import schedule
import time
import logging

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
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
            executor = RuleExecutor(rule_obj.id,False)
            executor.execute()
        except Exception as e:
            logger.error(f"[scheduler] Error running '{rule_name}': {e}")

    task.__name__ = f"task_{rule_name}"
    return task

from datetime import datetime
import schedule

def _build_schedule_jobs(db_job):
    jobs = []

    config = db_job.schedule_config or {}
    schedule_type = config.get("type")

    # ─────────────────────────────
    # 1. INTERVAL (existing + combos)
    # ─────────────────────────────
    if not schedule_type or schedule_type == "interval":

        combos = db_job.combinations or {}

        intervals = combos.get("intervals") or [db_job.interval]
        units     = combos.get("units")     or [db_job.unit]

        for interval in intervals:
            for unit in units:
                every = schedule.every(interval)

                unit_map = {
                    "seconds": every.seconds,
                    "minutes": every.minutes,
                    "hours":   every.hours,
                }

                job = unit_map.get(unit, every.seconds).do(
                    _make_task(db_job.rule_name)
                )

                jobs.append((job, interval, unit))

    # ─────────────────────────────
    # 2. DAILY AT TIME
    # ─────────────────────────────
    elif schedule_type == "daily":

        time_str = config.get("time", "00:00")

        job = schedule.every().day.at(time_str).do(
            _make_task(db_job.rule_name)
        )

        jobs.append((job, "daily", time_str))

    # ─────────────────────────────
    # 3. WEEKLY (selected days)
    # ─────────────────────────────
    elif schedule_type == "weekly":

        time_str = config.get("time", "00:00")
        days = config.get("days", [])

        day_map = {
            "monday": schedule.every().monday,
            "tuesday": schedule.every().tuesday,
            "wednesday": schedule.every().wednesday,
            "thursday": schedule.every().thursday,
            "friday": schedule.every().friday,
            "saturday": schedule.every().saturday,
            "sunday": schedule.every().sunday,
        }

        for d in days:
            sched = day_map.get(d.lower())
            if sched:
                job = sched.at(time_str).do(
                    _make_task(db_job.rule_name)
                )
                jobs.append((job, d, time_str))

    # ─────────────────────────────
    # 4. RUN ONCE
    # ─────────────────────────────
    elif schedule_type == "once":

        date_str = config.get("date")
        time_str = config.get("time", "00:00")

        def one_time_task():
            now = datetime.now()
            target = datetime.fromisoformat(f"{date_str}T{time_str}")

            if now >= target:
                _make_task(db_job.rule_name)()
                return schedule.CancelJob

        job = schedule.every(1).minutes.do(one_time_task)
        jobs.append((job, "once", f"{date_str} {time_str}"))

    return jobs

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
            sched_jobs = _registered_jobs.pop(job_id)

            for sched_job, _, __ in sched_jobs:
                schedule.cancel_job(sched_job)
            label = db_job.rule_name if db_job else job_id
            print(f"[scheduler] Cancelled job: {label}")

    # ── Register new active jobs / re-register changed ones ───────────────
    for job_id, db_job in db_jobs.items():
        if not db_job.is_active:
            continue

        existing = _registered_jobs.get(job_id)

        if existing is not None:
    # safest: always re-register if config exists
            if db_job.schedule_config or db_job.combinations:
                for sched_job, _, __ in existing:
                    schedule.cancel_job(sched_job)
                del _registered_jobs[job_id]
            else:
                sched_job, reg_interval, reg_unit = existing[0]
                if reg_interval == db_job.interval and reg_unit == db_job.unit:
                    continue
            schedule.cancel_job(sched_job)
            del _registered_jobs[job_id]
            print(f"[scheduler] Re-registering changed job: {db_job.rule_name}")

        sched_jobs = _build_schedule_jobs(db_job)
        _registered_jobs[job_id] = sched_jobs

        sched_jobs = _build_schedule_jobs(db_job)
        _registered_jobs[job_id] = sched_jobs

        for sched_job, meta1, meta2 in sched_jobs:
            print(f"[scheduler] Registered: {db_job.rule_name} — {meta1} {meta2}")
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
