"""SQLite database layer."""
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
    years_experience    TEXT,
    status              TEXT DEFAULT 'new',
    notes               TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT DEFAULT (datetime('now')),
    completed_at    TEXT,
    jobs_found      INTEGER DEFAULT 0,
    jobs_saved      INTEGER DEFAULT 0,
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
        # Migrate existing databases: add years_experience if missing
        cols = [row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        if "years_experience" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN years_experience TEXT")
        # Remove old AI columns gracefully — SQLite doesn't support DROP COLUMN
        # before v3.35, so we just leave them in place if they exist.


def upsert_job(job: dict[str, Any]) -> int | None:
    """Insert a new job or ignore if URL already exists. Returns new id or None."""
    sql = """
        INSERT OR IGNORE INTO jobs
            (title, company, location, url, site, description, salary, posted_date, years_experience)
        VALUES
            (:title, :company, :location, :url, :site, :description, :salary, :posted_date, :years_experience)
    """
    with get_conn() as conn:
        cur = conn.execute(sql, job)
        return cur.lastrowid if cur.lastrowid else None


def update_status(job_id: int, status: str) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    with get_conn() as conn:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))


def update_notes(job_id: int, notes: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE jobs SET notes=? WHERE id=?", (notes, job_id))


def get_job(job_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(
    status: str | None = None,
    site: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where_clauses: list[str] = []
    params: list[Any] = []
    if status:
        where_clauses.append("status = ?")
        params.append(status)
    if site:
        where_clauses.append("site = ?")
        params.append(site)
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    sql = f"""
        SELECT * FROM jobs {where}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


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


def finish_scrape_run(run_id: int, found: int, saved: int, error: str | None = None) -> None:
    status = "failed" if error else "completed"
    with get_conn() as conn:
        conn.execute(
            """UPDATE scrape_runs
               SET completed_at=datetime('now'), jobs_found=?, jobs_saved=?, status=?, error=?
               WHERE id=?""",
            (found, saved, status, error, run_id),
        )


def get_last_scrape_run() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None
