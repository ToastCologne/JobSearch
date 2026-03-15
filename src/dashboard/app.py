"""FastAPI web dashboard for reviewing and managing job applications."""
from fastapi import FastAPI, Form, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src import database as db
from src.config import load_config
from src.scheduler import is_running, next_run_time

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Legal Job Scraper")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

db.init_db()


# ─── Overview ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    counts = db.count_by_status()
    last_run = db.get_last_scrape_run()
    recent_jobs = db.list_jobs(limit=5)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "counts": counts,
            "last_run": last_run,
            "recent_jobs": recent_jobs,
            "scheduler_running": is_running(),
            "next_run": next_run_time(),
        },
    )


# ─── Jobs List ───────────────────────────────────────────────────────────────

@app.get("/jobs", response_class=HTMLResponse)
async def jobs_list(
    request: Request,
    status: str = "",
    site: str = "",
    page: int = 1,
):
    limit = 20
    offset = (page - 1) * limit
    jobs = db.list_jobs(
        status=status or None,
        site=site or None,
        limit=limit,
        offset=offset,
    )
    return templates.TemplateResponse(
        "jobs.html",
        {
            "request": request,
            "jobs": jobs,
            "status_filter": status,
            "site_filter": site,
            "page": page,
            "has_next": len(jobs) == limit,
        },
    )


# ─── Job Detail ──────────────────────────────────────────────────────────────

@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: int):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse("job_detail.html", {"request": request, "job": job})


@app.post("/jobs/{job_id}/status")
async def update_status(job_id: int, status: str = Form(...)):
    db.update_status(job_id, status)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/notes")
async def update_notes(job_id: int, notes: str = Form("")):
    db.update_notes(job_id, notes)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


# ─── Scrape Trigger ───────────────────────────────────────────────────────────

_scrape_running = False


@app.post("/scrape")
async def trigger_scrape(background_tasks: BackgroundTasks):
    global _scrape_running
    if _scrape_running:
        return RedirectResponse(url="/?msg=already_running", status_code=303)
    _scrape_running = True
    background_tasks.add_task(_run_scrape)
    return RedirectResponse(url="/?msg=scrape_started", status_code=303)


async def _run_scrape():
    global _scrape_running
    try:
        from src.pipeline import run_scrape_pipeline
        await run_scrape_pipeline(headless=True)
    finally:
        _scrape_running = False


@app.get("/scrape-status")
async def scrape_status():
    return {"running": _scrape_running}
