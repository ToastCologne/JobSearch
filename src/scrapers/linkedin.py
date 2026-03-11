"""LinkedIn job scraper."""
import asyncio
from typing import Any
from urllib.parse import quote_plus

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from src.scrapers.base import BaseScraper


class LinkedInScraper(BaseScraper):
    site_name = "linkedin"
    BASE_URL = "https://www.linkedin.com"

    async def scrape_jobs(
        self, queries: list[str], location: str, remote: bool = False
    ) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        page = await self.new_page()
        try:
            # Check if we're logged in
            await page.goto(f"{self.BASE_URL}/feed/", wait_until="domcontentloaded", timeout=30000)
            await self.human_delay(1000, 2000)

            if "login" in page.url or "authwall" in page.url:
                print(
                    "[LinkedIn] Not logged in. Please run with --login flag to "
                    "authenticate, then re-run the scraper."
                )
                return []

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
        params = f"keywords={quote_plus(query)}&location={quote_plus(location)}"
        if remote:
            params += "&f_WT=2"  # remote filter

        url = f"{self.BASE_URL}/jobs/search/?{params}"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await self.human_delay(2000, 3000)

        # Scroll to load more results
        for _ in range(3):
            await page.keyboard.press("End")
            await self.human_delay(1000, 2000)

        # Collect job cards
        cards = await page.query_selector_all("div.job-card-container")
        if not cards:
            cards = await page.query_selector_all("li.jobs-search-results__list-item")

        print(f"[LinkedIn] Found {len(cards)} cards for '{query}'")

        for card in cards[:25]:  # cap per query
            try:
                job = await self._extract_card(page, card)
                if job:
                    jobs.append(job)
            except Exception as e:
                print(f"[LinkedIn] Error extracting card: {e}")
            await self.human_delay(300, 800)

        return jobs

    async def _extract_card(self, page: Page, card) -> dict[str, Any] | None:
        try:
            title_el = await card.query_selector("a.job-card-list__title, .job-card-container__link")
            company_el = await card.query_selector(".job-card-container__company-name, .artdeco-entity-lockup__subtitle")
            location_el = await card.query_selector(".job-card-container__metadata-item")

            if not title_el:
                return None

            title = (await title_el.inner_text()).strip()
            company = (await company_el.inner_text()).strip() if company_el else "Unknown"
            location = (await location_el.inner_text()).strip() if location_el else ""

            href = await title_el.get_attribute("href")
            if not href:
                return None
            # Normalise URL
            if href.startswith("/"):
                href = f"https://www.linkedin.com{href}"
            url = href.split("?")[0]  # strip tracking params

            # Get description by clicking card
            description = ""
            salary = ""
            try:
                await card.click()
                await self.human_delay(1500, 2500)

                desc_el = await page.query_selector(".jobs-description-content__text, #job-details")
                if desc_el:
                    description = (await desc_el.inner_text()).strip()[:5000]

                salary_el = await page.query_selector(".compensation__salary-range, .jobs-unified-top-card__job-insight")
                if salary_el:
                    salary = (await salary_el.inner_text()).strip()
            except Exception:
                pass

            return {
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "site": "linkedin",
                "description": description,
                "salary": salary,
                "posted_date": "",
            }
        except Exception as e:
            print(f"[LinkedIn] Card extraction error: {e}")
            return None


async def open_login_page() -> None:
    """Open LinkedIn login page and wait for user to log in."""
    from src.scrapers.linkedin import LinkedInScraper
    async with LinkedInScraper(headless=False) as scraper:
        page = await scraper.new_page()
        await page.goto("https://www.linkedin.com/login")
        print("[LinkedIn] Please log in in the browser window. Press Enter when done...")
        input()
        await page.close()
