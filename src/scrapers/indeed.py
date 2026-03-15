"""Indeed job scraper."""
from typing import Any
from urllib.parse import quote_plus

from playwright.async_api import Page

from src.scrapers.base import BaseScraper


class IndeedScraper(BaseScraper):
    site_name = "indeed"
    BASE_URL = "https://www.indeed.com"  # international — works for Luxembourg

    async def scrape_jobs(
        self, queries: list[str], location: str, remote: bool = False
    ) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        page = await self.new_page()
        try:
            for query in queries:
                page_jobs = await self._search_query(page, query, location, remote)
                jobs.extend(page_jobs)
                await self.human_delay(2000, 4000)
        finally:
            await page.close()
        return jobs

    async def _search_query(
        self, page: Page, query: str, location: str, remote: bool
    ) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        params = f"q={quote_plus(query)}&l={quote_plus(location)}"
        if remote:
            params += "&remotejob=032b3046-06a3-4876-8dfd-474eb5e7ed11"

        url = f"{self.BASE_URL}/jobs?{params}"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"[Indeed] Navigation error: {e}")
            return []

        await self.human_delay(2000, 3000)

        # Dismiss cookie banner if present
        try:
            accept_btn = await page.query_selector("button#onetrust-accept-btn-handler")
            if accept_btn:
                await accept_btn.click()
                await self.human_delay(500, 1000)
        except Exception:
            pass

        cards = await page.query_selector_all("div.job_seen_beacon, li.css-1ac2h1w")
        print(f"[Indeed] Found {len(cards)} cards for '{query}'")

        for card in cards[:25]:
            try:
                job = await self._extract_card(page, card)
                if job:
                    jobs.append(job)
            except Exception as e:
                print(f"[Indeed] Card error: {e}")
            await self.human_delay(400, 900)

        return jobs

    async def _extract_card(self, page: Page, card) -> dict[str, Any] | None:
        try:
            title_el = await card.query_selector("h2.jobTitle a, a.jcs-JobTitle")
            company_el = await card.query_selector("[data-testid='company-name'], .companyName")
            location_el = await card.query_selector("[data-testid='text-location'], .companyLocation")
            salary_el = await card.query_selector("[data-testid='attribute_snippet_testid'], .salary-snippet")
            date_el = await card.query_selector("[data-testid='myJobsStateDate'], .date")

            if not title_el:
                return None

            title = (await title_el.inner_text()).strip()
            company = (await company_el.inner_text()).strip() if company_el else "Unknown"
            location = (await location_el.inner_text()).strip() if location_el else ""
            salary = (await salary_el.inner_text()).strip() if salary_el else ""
            posted_date = (await date_el.inner_text()).strip() if date_el else ""

            href = await title_el.get_attribute("href")
            if not href:
                return None
            url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

            # Get description
            description = ""
            try:
                await card.click()
                await self.human_delay(1500, 2500)
                desc_el = await page.query_selector(
                    "#jobDescriptionText, .jobsearch-jobDescriptionText"
                )
                if desc_el:
                    description = (await desc_el.inner_text()).strip()[:5000]
            except Exception:
                pass

            return {
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "site": "indeed",
                "description": description,
                "salary": salary,
                "posted_date": posted_date,
            }
        except Exception as e:
            print(f"[Indeed] Extraction error: {e}")
            return None
