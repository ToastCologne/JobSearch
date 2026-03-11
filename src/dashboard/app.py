"""FastAPI web dashboard for reviewing and managing job applications."""
import asyncio
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src import database as db
from src.ai.cover_letter import generate_cover_letter
from src.ai.cv_amender import amend_cv
from src.config import get_cv_path, get_output_dir, load_config
from src.cv_handler import apply_amendments, get_cv_text_for_ai
from src.scheduler import is_running, next_run_time

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Job Search Bot")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/output", StaticFiles(directory="output"), name="output")

db.init_db()


# ─── Overview ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    counts = db.count_by_status()
    last_run = db.get_last_scrape_run()
    recent_jobs = db.list_jobs(min_score=0, limit=5)
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
    min_score: int = 0,
    page: int = 1,
):
    limit = 20
    offset = (page - 1) * limit
    jobs = db.list_jobs(
        status=status or None,
        site=site or None,
        min_score=min_score,
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
            "min_score": min_score,
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

    cover_letter_text = ""
    if job.get("cover_letter_path"):
        cl_path = Path(job["cover_letter_path"])
        if cl_path.exists():
            cover_letter_text = cl_path.read_text()

    return templates.TemplateResponse(
        "job_detail.html",
        {
            "request": request,
            "job": job,
            "cover_letter_text": cover_letter_text,
        },
    )


@app.post("/jobs/{job_id}/status")
async def update_status(job_id: int, status: str = Form(...)):
    db.update_status(job_id, status)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/notes")
async def update_notes(job_id: int, notes: str = Form("")):
    db.update_job_field(job_id, "notes", notes)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


# ─── CV Amendment ────────────────────────────────────────────────────────────

_amend_tasks: dict[int, str] = {}  # job_id -> status


@app.post("/jobs/{job_id}/amend-cv")
async def start_amend_cv(job_id: int, background_tasks: BackgroundTasks):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404)
    _amend_tasks[job_id] = "running"
    background_tasks.add_task(_amend_cv_task, job_id, job)
    return RedirectResponse(url=f"/jobs/{job_id}?amend=pending", status_code=303)


async def _amend_cv_task(job_id: int, job: dict):
    try:
        cv_path = get_cv_path()
        cv_text = get_cv_text_for_ai(cv_path)
        amendments = await amend_cv(job, cv_text)

        output_dir = get_output_dir("cv")
        out_path = output_dir / f"job_{job_id}_cv.pptx"
        apply_amendments(cv_path, amendments, out_path)

        db.update_job_field(job_id, "cv_path", str(out_path))
        _amend_tasks[job_id] = "done"
    except Exception as e:
        print(f"[CV Amend] Error for job {job_id}: {e}")
        _amend_tasks[job_id] = f"error: {e}"


@app.get("/jobs/{job_id}/amend-status")
async def amend_status(job_id: int):
    return {"status": _amend_tasks.get(job_id, "idle")}


@app.get("/jobs/{job_id}/cv-download")
async def download_cv(job_id: int):
    job = db.get_job(job_id)
    if not job or not job.get("cv_path"):
        raise HTTPException(status_code=404, detail="No amended CV found")
    cv_path = Path(job["cv_path"])
    if not cv_path.exists():
        raise HTTPException(status_code=404, detail="CV file not found")
    return FileResponse(
        str(cv_path),
        filename=f"{job['company']}_{job['title']}_CV.pptx".replace(" ", "_"),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


# ─── Cover Letter ─────────────────────────────────────────────────────────────

_cl_tasks: dict[int, str] = {}


@app.post("/jobs/{job_id}/cover-letter")
async def start_cover_letter(job_id: int, background_tasks: BackgroundTasks):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404)
    _cl_tasks[job_id] = "running"
    background_tasks.add_task(_cover_letter_task, job_id, job)
    return RedirectResponse(url=f"/jobs/{job_id}?cl=pending", status_code=303)


async def _cover_letter_task(job_id: int, job: dict):
    try:
        cv_text = get_cv_text_for_ai(get_cv_path())
        letter = await generate_cover_letter(job, cv_text)

        output_dir = get_output_dir("cover_letters")
        out_path = output_dir / f"job_{job_id}_cover_letter.txt"
        out_path.write_text(letter)

        db.update_job_field(job_id, "cover_letter_path", str(out_path))
        _cl_tasks[job_id] = "done"
    except Exception as e:
        print(f"[Cover Letter] Error for job {job_id}: {e}")
        _cl_tasks[job_id] = f"error: {e}"


@app.get("/jobs/{job_id}/cl-status")
async def cl_status(job_id: int):
    return {"status": _cl_tasks.get(job_id, "idle")}


@app.get("/jobs/{job_id}/cover-letter-download")
async def download_cover_letter(job_id: int):
    job = db.get_job(job_id)
    if not job or not job.get("cover_letter_path"):
        raise HTTPException(status_code=404)
    cl_path = Path(job["cover_letter_path"])
    if not cl_path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(
        str(cl_path),
        filename=f"{job['company']}_{job['title']}_CoverLetter.txt".replace(" ", "_"),
        media_type="text/plain",
    )


# ─── Form Filler ─────────────────────────────────────────────────────────────

@app.post("/jobs/{job_id}/fill-form")
async def fill_form(job_id: int, background_tasks: BackgroundTasks):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404)
    background_tasks.add_task(_fill_form_task, job_id, job)
    return RedirectResponse(url=f"/jobs/{job_id}?form=pending", status_code=303)


async def _fill_form_task(job_id: int, job: dict):
    try:
        from src.form_filler import fill_application_form
        cv_path = get_cv_path()
        screenshot_path = await fill_application_form(job, cv_path, headless=False)
        if screenshot_path:
            db.update_job_field(job_id, "form_screenshot", screenshot_path)
    except Exception as e:
        print(f"[Form Filler] Error for job {job_id}: {e}")


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
