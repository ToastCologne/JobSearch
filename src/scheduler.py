"""APScheduler integration for scheduled scraping runs."""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def start_scheduler(cron_expr: str, job_func) -> None:
    """Start the scheduler with a cron expression and async job function."""
    scheduler = get_scheduler()
    if scheduler.running:
        return

    # Parse cron expression (5 fields: min hour dom month dow)
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr}")

    minute, hour, day, month, day_of_week = parts
    trigger = CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
    )

    scheduler.add_job(job_func, trigger=trigger, id="scrape_job", replace_existing=True)
    scheduler.start()
    print(f"[Scheduler] Started with cron: {cron_expr}")


def stop_scheduler() -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)


def is_running() -> bool:
    scheduler = get_scheduler()
    return scheduler.running


def next_run_time() -> str | None:
    scheduler = get_scheduler()
    if not scheduler.running:
        return None
    job = scheduler.get_job("scrape_job")
    if job and job.next_run_time:
        return job.next_run_time.strftime("%Y-%m-%d %H:%M %Z")
    return None
