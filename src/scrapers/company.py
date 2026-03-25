"""Company career page scraper — strict job-link detection."""
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Page

from src.scrapers.base import BaseScraper

# The URL *path* (not domain, not query string) must contain one of these
# for a link to be considered a job posting.  This eliminates footer links
# like /legal, /privacy, /terms, /about etc.
_JOB_PATH_SEGMENTS = [
    "/job/", "/jobs/", "/position/", "/positions/",
    "/role/", "/roles/", "/opening/", "/openings/",
    "/vacancy/", "/vacancies/", "/apply/",
    "/requisition/", "/posting/", "/opportunity/",
    "/offre/", "/emploi/",
]

# Link text that is definitely not a job title — exact, case-insensitive match.
_NON_JOB_TEXTS = frozenset([
    "legal", "legal notice", "legal disclaimer",
    "privacy", "privacy policy", "privacy notice",
    "terms", "terms of use", "terms and conditions",
    "cookie policy", "cookie notice", "cookies",
    "imprint", "disclaimer", "sitemap", "accessibility",
    "contact", "contact us", "about", "about us",
    "home", "back", "next", "previous",
    "sign in", "log in", "register",
    "apply now", "search jobs", "view all jobs",
    "load more", "show more", "careers", "job search",
])


class CompanyPageScraper(BaseScraper):
    site_name = "company"

    def __init__(self, company_pages: list[dict[str, str]], headless: bool = True):
        super().__init__(headless=headless)
        self.company_pages = company_pages  # [{name: str, url: str}]

    async def scrape_jobs(
        self, queries: list[str], location: str, remote: bool = False
    ) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        page = await self.new_page()
        try:
            for cp in self.company_pages:
                company_jobs = await self._scrape_page(page, cp["name"], cp["url"])
                jobs.extend(company_jobs)
                await self.human_delay(2000, 4000)
        finally:
            await page.close()
        return jobs

    async def _scrape_page(
        self, page: Page, company: str, url: str
    ) -> list[dict[str, Any]]:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"[{company}] Navigation error: {e}")
            return []

        # Extra wait for JS-heavy career portals
        await self.human_delay(3000, 5000)

        parsed_base = urlparse(url)
        base_domain = f"{parsed_base.scheme}://{parsed_base.netloc}"
        jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        links = await page.query_selector_all("a[href]")

        for link in links:
            try:
                # Skip anything inside nav / header / footer — never a job card
                in_chrome = await link.evaluate(
                    "el => !!el.closest('nav, footer, header,"
                    " [role=\"navigation\"], [role=\"banner\"]')"
                )
                if in_chrome:
                    continue

                text = (await link.inner_text()).strip()
                href = (await link.get_attribute("href") or "").strip()

                if not text or not href:
                    continue
                if len(text) > 150 or len(text) < 5:
                    continue

                # Drop known non-job link texts
                if text.lower() in _NON_JOB_TEXTS:
                    continue

                # Build absolute URL
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/"):
                    full_url = f"{base_domain}{href}"
                else:
                    continue

                # The URL path must contain a job-specific segment
                path = urlparse(full_url).path.lower()
                if not any(seg in path for seg in _JOB_PATH_SEGMENTS):
                    continue

                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                jobs.append({
                    "title": text,   # may be replaced by real <h1> below
                    "company": company,
                    "location": "",
                    "url": full_url,
                    "site": "company",
                    "description": "",
                    "salary": "",
                    "posted_date": "",
                })
            except Exception:
                continue

        print(f"[{company}] Found {len(jobs)} job links on listing page")

        # Visit each job detail page: get real title, location, description
        for job in jobs[:20]:
            try:
                detail = await self.new_page()
                await detail.goto(job["url"], wait_until="domcontentloaded", timeout=25000)
                await self.human_delay(1000, 2000)

                # Prefer the <h1> as the canonical job title
                h1 = await detail.query_selector("h1")
                if h1:
                    real_title = (await h1.inner_text()).strip()
                    if real_title:
                        job["title"] = real_title

                # Try common location selectors
                for sel in [
                    "[class*='location' i]", "[data-testid*='location' i]",
                    "[class*='Location']", ".job-location", "[class*='city' i]",
                ]:
                    loc_el = await detail.query_selector(sel)
                    if loc_el:
                        loc_text = (await loc_el.inner_text()).strip()
                        if loc_text:
                            job["location"] = loc_text
                            break

                # Description from the main content area
                body = await detail.query_selector(
                    "main, article, [class*='description' i],"
                    " [class*='job-detail' i], body"
                )
                if body:
                    job["description"] = (await body.inner_text()).strip()[:5000]

                await detail.close()
            except Exception:
                pass
            await self.human_delay(600, 1400)

        return jobs
