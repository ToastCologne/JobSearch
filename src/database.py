"""SQLite database layer."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator

from src.config import get_db_path

DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT NOT NULL,
    company             TEXT NOT NULL,
    location            TEXT,
    url                 TEXT UNIQUE NOT NULL,
    site                TEXT NOT NULL,
    description         TEXT,
    salary              TEXT,
    posted_date         TEXT,
    status              TEXT DEFAULT 'new',
    match_score         INTEGER,
    match_reasons       TEXT,
    cv_path             TEXT,
    cover_letter_path   TEXT,
    form_screenshot     TEXT,
    notes               TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT DEFAULT (datetime('now')),
    completed_at    TEXT,
    jobs_found      INTEGER DEFAULT 0,
    jobs_matched    INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'running',
    error           TEXT
);

CREATE TRIGGER IF NOT EXISTS jobs_updated_at
    AFTER UPDATE ON jobs
    BEGIN
        UPDATE jobs SET updated_at = datetime('now') WHERE id = NEW.id;
    END;
"""

VALID_STATUSES = {"new", "reviewing", "interested", "applied", "rejected", "archived"}


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(DDL)


def upsert_job(job: dict[str, Any]) -> int | None:
    """Insert a new job or ignore if URL already exists. Returns new id or None."""
    sql = """
        INSERT OR IGNORE INTO jobs
            (title, company, location, url, site, description, salary, posted_date)
        VALUES
            (:title, :company, :location, :url, :site, :description, :salary, :posted_date)
    """
    with get_conn() as conn:
        cur = conn.execute(sql, job)
        return cur.lastrowid if cur.lastrowid else None


def update_match(job_id: int, score: int, reasons: list[str]) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET match_score=?, match_reasons=?, status='reviewing' WHERE id=?",
            (score, json.dumps(reasons), job_id),
        )


def update_status(job_id: int, status: str) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    with get_conn() as conn:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))


def update_job_field(job_id: int, field: str, value: str) -> None:
    allowed = {"cv_path", "cover_letter_path", "form_screenshot", "notes"}
    if field not in allowed:
        raise ValueError(f"Cannot update field: {field}")
    with get_conn() as conn:
        conn.execute(f"UPDATE jobs SET {field}=? WHERE id=?", (value, job_id))


def get_job(job_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    if d.get("match_reasons"):
        d["match_reasons"] = json.loads(d["match_reasons"])
    return d


def list_jobs(
    status: str | None = None,
    site: str | None = None,
    min_score: int = 0,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where_clauses = [f"match_score >= {min_score}"]
    params: list[Any] = []
    if status:
        where_clauses.append("status = ?")
        params.append(status)
    if site:
        where_clauses.append("site = ?")
        params.append(site)
    where = " AND ".join(where_clauses)
    sql = f"""
        SELECT * FROM jobs WHERE {where}
        ORDER BY match_score DESC, created_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        if d.get("match_reasons"):
            d["match_reasons"] = json.loads(d["match_reasons"])
        result.append(d)
    return result


def count_by_status() -> dict[str, int]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status"
        ).fetchall()
    return {row["status"]: row["cnt"] for row in rows}


def start_scrape_run() -> int:
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO scrape_runs DEFAULT VALUES")
        return cur.lastrowid


def finish_scrape_run(run_id: int, found: int, matched: int, error: str | None = None) -> None:
    status = "failed" if error else "completed"
    with get_conn() as conn:
        conn.execute(
            """UPDATE scrape_runs
               SET completed_at=datetime('now'), jobs_found=?, jobs_matched=?, status=?, error=?
               WHERE id=?""",
            (found, matched, status, error, run_id),
        )


def get_last_scrape_run() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None
