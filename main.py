#!/usr/bin/env python3
"""Job Search Bot — CLI entry point.

Usage:
    python main.py setup          # Install Playwright browsers, init DB
    python main.py scrape         # Run a one-off scrape + match
    python main.py dashboard      # Start the web dashboard
    python main.py login linkedin  # Open browser to log in to a site
    python main.py login glassdoor
"""
import asyncio
import sys


def cmd_setup():
    """Install Playwright browsers and initialise the database."""
    import subprocess

    print("Installing Playwright browsers...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=False,
    )
    if result.returncode != 0:
        print("Warning: Playwright browser install may have failed.")

    print("Initialising database...")
    from src import database as db
    db.init_db()
    print("Done. Setup complete.")


def cmd_scrape(headless: bool = True):
    """Run the scraping pipeline."""
    from src.pipeline import run_scrape_pipeline
    stats = asyncio.run(run_scrape_pipeline(headless=headless))
    print(f"\nScrape complete: {stats['found']} found, {stats['matched']} matched.")


def cmd_dashboard():
    """Start the FastAPI web dashboard."""
    import uvicorn
    from src.config import load_config
    from src.database import init_db

    init_db()
    cfg = load_config()

    # Start scheduler if enabled
    scheduler_cfg = cfg.get("scheduler", {})
    if scheduler_cfg.get("enabled"):
        from src.pipeline import run_scrape_pipeline
        from src.scheduler import start_scheduler
        cron = scheduler_cfg.get("cron", "0 9 * * 1-5")
        start_scheduler(cron, lambda: asyncio.ensure_future(run_scrape_pipeline()))
        print(f"[Scheduler] Enabled with cron: {cron}")

    host = cfg.get("dashboard", {}).get("host", "127.0.0.1")
    port = cfg.get("dashboard", {}).get("port", 8000)

    print(f"\nStarting dashboard at http://{host}:{port}")
    print("Press Ctrl+C to stop.\n")

    uvicorn.run(
        "src.dashboard.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


async def cmd_login(site: str):
    """Open a browser window to let the user log in to a job site."""
    site = site.lower()
    if site == "linkedin":
        from src.scrapers.linkedin import LinkedInScraper
        print(f"Opening {site} login page. Log in, then press Enter...")
        async with LinkedInScraper(headless=False) as scraper:
            page = await scraper.new_page()
            await page.goto("https://www.linkedin.com/login")
            input("Press Enter when logged in...")
            await page.close()
    elif site == "glassdoor":
        from src.scrapers.glassdoor import GlassdoorScraper
        print(f"Opening {site} login page. Log in, then press Enter...")
        async with GlassdoorScraper(headless=False) as scraper:
            page = await scraper.new_page()
            await page.goto("https://www.glassdoor.co.uk/profile/login_input.htm")
            input("Press Enter when logged in...")
            await page.close()
    elif site == "indeed":
        from src.scrapers.indeed import IndeedScraper
        print(f"Opening {site} login page. Log in, then press Enter...")
        async with IndeedScraper(headless=False) as scraper:
            page = await scraper.new_page()
            await page.goto("https://secure.indeed.com/account/login")
            input("Press Enter when logged in...")
            await page.close()
    else:
        print(f"Unknown site: {site}. Supported: linkedin, glassdoor, indeed")
        sys.exit(1)

    print(f"Session saved for {site}. You won't need to log in again.")


def print_help():
    print(__doc__)


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print_help()
        return

    cmd = args[0]

    if cmd == "setup":
        cmd_setup()

    elif cmd == "scrape":
        headless = "--visible" not in args
        cmd_scrape(headless=headless)

    elif cmd == "dashboard":
        cmd_dashboard()

    elif cmd == "login":
        if len(args) < 2:
            print("Usage: python main.py login <site>  (linkedin|glassdoor|indeed)")
            sys.exit(1)
        asyncio.run(cmd_login(args[1]))

    else:
        print(f"Unknown command: {cmd}")
        print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
