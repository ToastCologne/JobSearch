"""Company career page scraper (generic)."""
from typing import Any

from playwright.async_api import Page

from src.scrapers.base import BaseScraper


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

        await self.human_delay(2000, 3000)
        jobs: list[dict[str, Any]] = []

        # Generic job link detection — looks for <a> tags with common job keywords
        links = await page.query_selector_all("a")
        seen_urls: set[str] = set()

        for link in links:
            try:
                text = (await link.inner_text()).strip()
                href = await link.get_attribute("href") or ""

                # Filter for plausible job listing links
                if not text or len(text) > 120 or len(text) < 5:
                    continue
                if not any(
                    kw in href.lower()
                    for kw in ["job", "career", "position", "role", "opening", "vacancy"]
                ):
                    if not any(
                        kw in text.lower()
                        for kw in ["engineer", "developer", "manager", "analyst", "designer"]
                    ):
                        continue

                # Build absolute URL
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/"):
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    full_url = f"{parsed.scheme}://{parsed.netloc}{href}"
                else:
                    continue

                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                jobs.append({
                    "title": text,
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

        print(f"[{company}] Found {len(jobs)} potential job links")

        # Fetch description for first N jobs
        for job in jobs[:15]:
            try:
                desc_page = await self.new_page()
                await desc_page.goto(job["url"], wait_until="domcontentloaded", timeout=20000)
                await self.human_delay(1000, 2000)
                body = await desc_page.query_selector("main, article, .content, body")
                if body:
                    job["description"] = (await body.inner_text()).strip()[:5000]
                await desc_page.close()
            except Exception:
                pass
            await self.human_delay(500, 1500)

        return jobs
