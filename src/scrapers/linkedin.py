"""LinkedIn job scraper."""
import asyncio
from typing import Any
from urllib.parse import quote_plus

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from src.scrapers.base import BaseScraper


class LinkedInScraper(BaseScraper):
    site_name = "linkedin"
    BASE_URL = "https://www.linkedin.com"

    async def _ensure_logged_in(self) -> bool:
        """
        Check if LinkedIn session is active. If not, open a visible browser
        window so the user can log in, then switch back to headless mode.
        Returns True when a valid session exists.
        """
        page = await self.new_page()
        try:
            await page.goto(
                f"{self.BASE_URL}/feed/", wait_until="domcontentloaded", timeout=30000
            )
            await self.human_delay(1000, 2000)
            already_logged_in = "login" not in page.url and "authwall" not in page.url
        finally:
            await page.close()

        if already_logged_in:
            return True

        # ── Not logged in: reopen browser as visible window ──────────────
        print(
            "[LinkedIn] No active session found.\n"
            "[LinkedIn] Opening a browser window for login — please sign in, "
            "then wait (up to 2 minutes)."
        )
        await self._open_context(headless=False)
        login_page = await self.new_page()
        await login_page.goto("https://www.linkedin.com/login")

        try:
            # Wait until LinkedIn redirects to the feed after successful login
            await login_page.wait_for_url("**/feed/**", timeout=120_000)
            print("[LinkedIn] Login detected — session saved. Continuing scrape...")
        except PlaywrightTimeout:
            print("[LinkedIn] Login timed out (2 min). Skipping LinkedIn this run.")
            await login_page.close()
            await self._open_context(self.headless)
            return False

        await login_page.close()
        # Switch back to original headless mode now that cookies are saved
        await self._open_context(self.headless)
        return True

    async def scrape_jobs(
        self, queries: list[str], location: str, remote: bool = False
    ) -> list[dict[str, Any]]:
        if not await self._ensure_logged_in():
            return []

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
        params = f"keywords={quote_plus(query)}&location={quote_plus(location)}"
        if remote:
            params += "&f_WT=2"

        url = f"{self.BASE_URL}/jobs/search/?{params}"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await self.human_delay(2000, 3000)

        for _ in range(3):
            await page.keyboard.press("End")
            await self.human_delay(1000, 2000)

        cards = await page.query_selector_all("div.job-card-container")
        if not cards:
            cards = await page.query_selector_all("li.jobs-search-results__list-item")

        print(f"[LinkedIn] Found {len(cards)} cards for '{query}' in {location}")

        for card in cards[:25]:
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
            title_el = await card.query_selector(
                "a.job-card-list__title, .job-card-container__link"
            )
            company_el = await card.query_selector(
                ".job-card-container__company-name, .artdeco-entity-lockup__subtitle"
            )
            location_el = await card.query_selector(".job-card-container__metadata-item")

            if not title_el:
                return None

            title = (await title_el.inner_text()).strip()
            company = (await company_el.inner_text()).strip() if company_el else "Unknown"
            location = (await location_el.inner_text()).strip() if location_el else ""

            href = await title_el.get_attribute("href")
            if not href:
                return None
            if href.startswith("/"):
                href = f"https://www.linkedin.com{href}"
            url = href.split("?")[0]

            description = ""
            salary = ""
            try:
                await card.click()
                await self.human_delay(1500, 2500)
                desc_el = await page.query_selector(
                    ".jobs-description-content__text, #job-details"
                )
                if desc_el:
                    description = (await desc_el.inner_text()).strip()[:5000]
                salary_el = await page.query_selector(
                    ".compensation__salary-range, .jobs-unified-top-card__job-insight"
                )
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
