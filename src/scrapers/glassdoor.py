"""Glassdoor job scraper."""
from typing import Any
from urllib.parse import quote_plus

from playwright.async_api import Page

from src.scrapers.base import BaseScraper


class GlassdoorScraper(BaseScraper):
    site_name = "glassdoor"
    BASE_URL = "https://www.glassdoor.co.uk"

    async def scrape_jobs(
        self, queries: list[str], location: str, remote: bool = False
    ) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        page = await self.new_page()
        try:
            # Check login
            await page.goto(f"{self.BASE_URL}/member/home/index.htm", wait_until="domcontentloaded", timeout=30000)
            await self.human_delay(1500, 2500)

            if "login" in page.url or "signin" in page.url:
                print(
                    "[Glassdoor] Not logged in. Run with --login glassdoor to authenticate."
                )
                return []

            for query in queries:
                page_jobs = await self._search_query(page, query, location, remote)
                jobs.extend(page_jobs)
                await self.human_delay(2500, 4500)
        finally:
            await page.close()
        return jobs

    async def _search_query(
        self, page: Page, query: str, location: str, remote: bool
    ) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        params = f"keyword={quote_plus(query)}&locT=N&locId=3&locKeyword={quote_plus(location)}"
        if remote:
            params += "&remoteWorkType=1"

        url = f"{self.BASE_URL}/Jobs/jobs.htm?{params}"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"[Glassdoor] Navigation error: {e}")
            return []

        await self.human_delay(2000, 3500)

        # Dismiss modals (login prompts, cookie banners)
        for selector in [
            "button[data-test='modal-close-btn']",
            "button.modal_closeIcon",
            "#onetrust-accept-btn-handler",
        ]:
            try:
                btn = await page.query_selector(selector)
                if btn:
                    await btn.click()
                    await self.human_delay(500, 1000)
            except Exception:
                pass

        cards = await page.query_selector_all(
            "li.JobsList_jobListItem__JBBUV, article[data-test='jobListing']"
        )
        print(f"[Glassdoor] Found {len(cards)} cards for '{query}'")

        for card in cards[:20]:
            try:
                job = await self._extract_card(page, card)
                if job:
                    jobs.append(job)
            except Exception as e:
                print(f"[Glassdoor] Card error: {e}")
            await self.human_delay(500, 1200)

        return jobs

    async def _extract_card(self, page: Page, card) -> dict[str, Any] | None:
        try:
            title_el = await card.query_selector(
                "a[data-test='job-title'], .JobCard_jobTitle__GLyJ1"
            )
            company_el = await card.query_selector(
                "[data-test='employer-name'], .EmployerProfile_profileContainer__d5rMb"
            )
            location_el = await card.query_selector(
                "[data-test='emp-location'], .JobCard_location__N_iYE"
            )
            salary_el = await card.query_selector(
                "[data-test='detailSalary'], .JobCard_salaryEstimate__QpbTW"
            )

            if not title_el:
                return None

            title = (await title_el.inner_text()).strip()
            company = (await company_el.inner_text()).strip() if company_el else "Unknown"
            location = (await location_el.inner_text()).strip() if location_el else ""
            salary = (await salary_el.inner_text()).strip() if salary_el else ""

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
                    ".JobDetails_jobDescription__uW_fK, [data-test='description']"
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
                "site": "glassdoor",
                "description": description,
                "salary": salary,
                "posted_date": "",
            }
        except Exception as e:
            print(f"[Glassdoor] Extraction error: {e}")
            return None
