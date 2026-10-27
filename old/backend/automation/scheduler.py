# myproject/scheduler.py

import os
import django
import time
import schedule
import logging
from datetime import datetime
from threading import Thread

# ─────────────────────────────────────────────────────────────
# Django setup
# ─────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "automation.settings")
django.setup()

from rule_engine.models import RuleEngine, ScheduledJob
from rule_engine.executor import GraphRuleExecutor as RuleExecutor

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# In-memory job registry
# { job_id: [(schedule.Job, meta1, meta2), ...] }
# ─────────────────────────────────────────────────────────────
_registered_jobs: dict[int, list] = {}


# ─────────────────────────────────────────────────────────────
# Task factory
# ─────────────────────────────────────────────────────────────
def _make_task(rule_name: str):
    def task():
        try:
            print(f"[scheduler] Running rule: {rule_name} at {datetime.utcnow().isoformat()}")

            rule_obj = RuleEngine.objects.filter(rule_name=rule_name).first()
            if not rule_obj:
                logger.warning(f"[scheduler] Rule '{rule_name}' not found")
                return

            executor = RuleExecutor(rule_obj.id, False)
            executor.execute()

        except Exception as e:
            logger.error(f"[scheduler] Error running '{rule_name}': {e}")

    task.__name__ = f"task_{rule_name}"
    return task


# ─────────────────────────────────────────────────────────────
# Build schedule jobs from DB config
# ─────────────────────────────────────────────────────────────
def _build_schedule_jobs(db_job):
    jobs = []

    config = db_job.schedule_config or {}
    schedule_type = config.get("type")

    # ── INTERVAL ─────────────────────────────────────────────
    if not schedule_type or schedule_type == "interval":

        combos = db_job.combinations or {}

        intervals = combos.get("intervals") or [db_job.interval]
        units = combos.get("units") or [db_job.unit]

        for interval in intervals:
            for unit in units:
                every = schedule.every(interval)

                unit_map = {
                    "seconds": every.seconds,
                    "minutes": every.minutes,
                    "hours": every.hours,
                }

                job = unit_map.get(unit, every.seconds).do(
                    _make_task(db_job.rule_name)
                )

                jobs.append((job, interval, unit))

    # ── DAILY ────────────────────────────────────────────────
    elif schedule_type == "daily":

        time_str = config.get("time", "00:00")

        job = schedule.every().day.at(time_str).do(
            _make_task(db_job.rule_name)
        )

        jobs.append((job, "daily", time_str))

    # ── WEEKLY ───────────────────────────────────────────────
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

    # ── ONCE ─────────────────────────────────────────────────
    elif schedule_type == "once":

        date_str = config.get("date")
        time_str = config.get("time", "00:00")

        def one_time_task():
            now = datetime.utcnow()
            target = datetime.fromisoformat(f"{date_str}").utcnow()

            if now >= target:
                _make_task(db_job.rule_name)()
                return schedule.CancelJob

        job = schedule.every(1).minutes.do(one_time_task)
        jobs.append((job, "once", f"{date_str} {time_str}"))

    return jobs


# ─────────────────────────────────────────────────────────────
# PUBLIC API FUNCTIONS (call from your Django views/services)
# ─────────────────────────────────────────────────────────────

def add_job(job_id: int):
    db_job = ScheduledJob.objects.filter(id=job_id).first()

    if not db_job:
        print(f"[scheduler] Job {job_id} not found or inactive")
        return

    # overwrite safely
    remove_job(job_id)

    sched_jobs = _build_schedule_jobs(db_job)

    _registered_jobs[job_id] = sched_jobs

    for sched_job, meta1, meta2 in sched_jobs:
        print(f"[scheduler] Registered: {db_job.rule_name} — {meta1} {meta2}")


def remove_job(job_id: int):
    existing = _registered_jobs.pop(job_id, None)

    if not existing:
        return

    for sched_job, _, __ in existing:
        schedule.cancel_job(sched_job)

    print(f"[scheduler] Removed job: {job_id}")


def update_job(job_id: int):
    remove_job(job_id)
    add_job(job_id)


def list_jobs():
    return list(_registered_jobs.keys())


# ─────────────────────────────────────────────────────────────
# Scheduler runner (run ONCE)
# ─────────────────────────────────────────────────────────────
def load_diff_jobs():
    new_jobs = ScheduledJob.objects.filter(is_active=True).all()
    for job in new_jobs:
        if job.id not in _registered_jobs:
            add_job(job.id)
    for jobs in list(_registered_jobs.keys()):
        if jobs not in [j.id for j in new_jobs]:
            remove_job(jobs)


def _run_scheduler():
    print("[scheduler] Started...")
    while True:
        schedule.run_pending()
        time.sleep(10)
        load_diff_jobs()
        print(f"Total Jobs {len(list_jobs())}")



def start_scheduler_in_background():
    thread = Thread(target=_run_scheduler, daemon=True)
    thread.start()
    print("[scheduler] Background thread started")


# ─────────────────────────────────────────────────────────────
# OPTIONAL: preload active jobs on startup
# ─────────────────────────────────────────────────────────────
def load_active_jobs():
    jobs = ScheduledJob.objects.filter(is_active=True).all()

    for job in jobs:
        add_job(job.id)

    print(f"[scheduler] Loaded {len(jobs)} jobs from DB")

if __name__ == "__main__":
    load_active_jobs()
    _run_scheduler()