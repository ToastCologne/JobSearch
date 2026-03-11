"""Main scrape-and-match pipeline."""
import asyncio
from pathlib import Path

from src import database as db
from src.ai.matcher import match_job
from src.config import get_cv_path, load_config
from src.cv_handler import get_cv_text_for_ai
from src.scrapers.company import CompanyPageScraper
from src.scrapers.glassdoor import GlassdoorScraper
from src.scrapers.indeed import IndeedScraper
from src.scrapers.linkedin import LinkedInScraper


async def run_scrape_pipeline(headless: bool = True) -> dict:
    """Run the full scraping and matching pipeline. Returns stats dict."""
    cfg = load_config()
    search = cfg.get("search", {})
    queries = search.get("queries", [])
    location = search.get("location", "")
    remote = search.get("remote", False)
    sites = search.get("sites", {})
    company_pages = search.get("company_pages", [])
    min_score = cfg.get("matching", {}).get("min_score", 50)

    cv_text = get_cv_text_for_ai(get_cv_path())

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

    print(f"\n[Pipeline] Total jobs found: {len(all_jobs)}")

    # --- Apply keyword hard filters ---
    required_kw = cfg.get("matching", {}).get("required_keywords", [])
    excluded_kw = cfg.get("matching", {}).get("excluded_keywords", [])
    if required_kw or excluded_kw:
        filtered = []
        for j in all_jobs:
            text = f"{j.get('title','')} {j.get('description','')}".lower()
            if required_kw and not all(k.lower() in text for k in required_kw):
                continue
            if excluded_kw and any(k.lower() in text for k in excluded_kw):
                continue
            filtered.append(j)
        print(f"[Pipeline] After keyword filters: {len(filtered)} jobs")
        all_jobs = filtered

    # --- Store new jobs and run AI matching ---
    matched = 0
    for job in all_jobs:
        new_id = db.upsert_job(job)
        if new_id is None:
            continue  # Already in DB

        job["id"] = new_id

        # AI match
        try:
            score, reasons = await match_job(job, cv_text, cfg)
            db.update_match(new_id, score, reasons)
            if score >= min_score:
                matched += 1
            print(f"  [{score:3d}] {job['title']} @ {job['company']}")
        except Exception as e:
            print(f"  [ERR] Could not score job {new_id}: {e}")

        await asyncio.sleep(0.5)  # Gentle rate limiting for Claude API

    db.finish_scrape_run(run_id, found=len(all_jobs), matched=matched)
    print(f"\n[Pipeline] Done. {matched} jobs scored above {min_score}.")
    return {"found": len(all_jobs), "matched": matched}
