"""Main scraping pipeline — keyword-based filtering, no AI."""
import re
from typing import Any

from src import database as db
from src.config import load_config
from src.scrapers.company import CompanyPageScraper
from src.scrapers.glassdoor import GlassdoorScraper
from src.scrapers.indeed import IndeedScraper
from src.scrapers.linkedin import LinkedInScraper


# ---------------------------------------------------------------------------
# Language exclusion — patterns that indicate a non-English language is required
# ---------------------------------------------------------------------------

_LANG_PATTERNS = [
    # "fluent in French", "proficient in German", "speak Luxembourgish"
    r"(?:fluent|proficient|native|speak(?:ing)?|written|spoken)\s+(?:in\s+)?{lang}",
    # "French language required", "German speaker", "Luxembourgish mandatory"
    r"{lang}\s+(?:language|speaker|speaking|fluency|proficiency|required|mandatory|essential|preferred)",
    # "languages: French", "languages required: German"
    r"languages?\s*(?:required|needed|mandatory|essential)?[^.]*\b{lang}\b",
    # "English and French", "French and English"
    r"english\s+(?:and|or)\s+{lang}",
    r"{lang}\s+(?:and|or)\s+english",
    # "bilingual French/English"
    r"bilingual[^.]*\b{lang}\b",
]


def _requires_excluded_language(text: str, languages: list[str]) -> bool:
    """Return True if the text indicates one of the listed languages is required."""
    for lang in languages:
        for pattern_tpl in _LANG_PATTERNS:
            pattern = pattern_tpl.format(lang=re.escape(lang))
            if re.search(pattern, text, re.IGNORECASE):
                return True
    return False


# ---------------------------------------------------------------------------
# Years-of-experience extraction
# ---------------------------------------------------------------------------

_EXP_PATTERNS = [
    # "5-8 years of experience" / "5 to 8 years"
    (r"(\d+)\s*(?:to|-)\s*(\d+)\s*\+?\s*years?\s*(?:of\s+)?(?:relevant\s+)?experience", "range"),
    # "5+ years of experience"
    (r"(\d+)\s*\+\s*years?\s*(?:of\s+)?(?:relevant\s+)?experience", "plus"),
    # "minimum 5 years" / "at least 5 years"
    (r"(?:minimum|at\s+least|min\.?)\s+(\d+)\s*\+?\s*years?\s*(?:of\s+)?(?:relevant\s+)?experience", "min"),
    # plain "5 years of experience"
    (r"(\d+)\s*years?\s*(?:of\s+)?(?:relevant\s+)?experience", "plain"),
    # "experience: 5+ years" (label style)
    (r"experience\s*[:\-]\s*(\d+)\s*\+?\s*years?", "label"),
]


def extract_years_experience(text: str) -> str | None:
    """Parse years-of-experience from a job description."""
    for pattern, kind in _EXP_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        if kind == "range":
            return f"{m.group(1)}–{m.group(2)} years"
        if kind == "plus":
            return f"{m.group(1)}+ years"
        if kind in ("min", "label", "plain"):
            raw = m.group(0)
            suffix = "+ years" if "+" in raw else " years"
            return f"{m.group(1)}{suffix}"
    return None


# ---------------------------------------------------------------------------
# Keyword filters (title + description)
# ---------------------------------------------------------------------------

def _passes_keyword_filters(job: dict[str, Any], required: list[str], excluded: list[str]) -> bool:
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    # Strip empty strings from lists (config placeholders)
    required = [k for k in required if k]
    excluded = [k for k in excluded if k]
    if required and not all(k.lower() in text for k in required):
        return False
    if excluded and any(k.lower() in text for k in excluded):
        return False
    return True


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def run_scrape_pipeline(headless: bool = True) -> dict:
    """Scrape jobs, apply filters, store new results. Returns stats dict."""
    cfg = load_config()
    search = cfg.get("search", {})
    queries = search.get("queries", [])
    location = search.get("location", "")
    remote = search.get("remote", False)
    sites = search.get("sites", {})
    company_pages = search.get("company_pages", [])

    matching = cfg.get("matching", {})
    required_kw = matching.get("required_keywords", [])
    excluded_kw = matching.get("excluded_keywords", [])
    excluded_langs = matching.get("exclude_languages", ["French", "German", "Luxembourgish"])

    run_id = db.start_scrape_run()
    all_jobs: list[dict] = []

    # --- Scrape each enabled site ---
    if sites.get("linkedin"):
        print("[Pipeline] Scraping LinkedIn...")
        try:
            async with LinkedInScraper(headless=headless) as scraper:
                jobs = await scraper.scrape_jobs(queries, location, remote)
                all_jobs.extend(jobs)
                print(f"[Pipeline] LinkedIn: {len(jobs)} jobs")
        except Exception as e:
            print(f"[Pipeline] LinkedIn error: {e}")

    if sites.get("indeed"):
        print("[Pipeline] Scraping Indeed...")
        try:
            async with IndeedScraper(headless=headless) as scraper:
                jobs = await scraper.scrape_jobs(queries, location, remote)
                all_jobs.extend(jobs)
                print(f"[Pipeline] Indeed: {len(jobs)} jobs")
        except Exception as e:
            print(f"[Pipeline] Indeed error: {e}")

    if sites.get("glassdoor"):
        print("[Pipeline] Scraping Glassdoor...")
        try:
            async with GlassdoorScraper(headless=headless) as scraper:
                jobs = await scraper.scrape_jobs(queries, location, remote)
                all_jobs.extend(jobs)
                print(f"[Pipeline] Glassdoor: {len(jobs)} jobs")
        except Exception as e:
            print(f"[Pipeline] Glassdoor error: {e}")

    if company_pages:
        print(f"[Pipeline] Scraping {len(company_pages)} company page(s)...")
        try:
            async with CompanyPageScraper(company_pages, headless=headless) as scraper:
                jobs = await scraper.scrape_jobs(queries, location, remote)
                all_jobs.extend(jobs)
                print(f"[Pipeline] Company pages: {len(jobs)} jobs")
        except Exception as e:
            print(f"[Pipeline] Company pages error: {e}")

    print(f"\n[Pipeline] Total jobs scraped: {len(all_jobs)}")

    # --- Apply filters ---
    filtered: list[dict] = []
    for job in all_jobs:
        desc = job.get("description", "") or ""
        title = job.get("title", "") or ""
        full_text = f"{title} {desc}"

        # 1. Keyword hard filters
        if not _passes_keyword_filters(job, required_kw, excluded_kw):
            continue

        # 2. Language exclusion filter
        if _requires_excluded_language(full_text, excluded_langs):
            print(f"  [SKIP] Language requirement: {title} @ {job.get('company', '')}")
            continue

        # 3. Extract years of experience
        job["years_experience"] = extract_years_experience(full_text)

        filtered.append(job)

    print(f"[Pipeline] After filters: {len(filtered)} jobs")

    # --- Store new jobs ---
    saved = 0
    for job in filtered:
        # Ensure all required fields exist
        job.setdefault("salary", "")
        job.setdefault("posted_date", "")
        job.setdefault("location", "")
        job.setdefault("description", "")
        job.setdefault("years_experience", None)

        new_id = db.upsert_job(job)
        if new_id:
            saved += 1
            print(f"  [NEW] {job['title']} @ {job['company']}"
                  + (f" ({job['years_experience']})" if job.get("years_experience") else ""))

    db.finish_scrape_run(run_id, found=len(all_jobs), saved=saved)
    print(f"\n[Pipeline] Done. {saved} new jobs saved (out of {len(filtered)} that passed filters).")
    return {"found": len(all_jobs), "saved": saved}
