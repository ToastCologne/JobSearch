"""Base scraper with persistent Playwright browser context."""
import asyncio
import random
from abc import ABC, abstractmethod
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

from src.config import get_browser_profile_dir


class BaseScraper(ABC):
    """Base class for all job site scrapers.

    Uses a persistent browser context to maintain session cookies
    across runs (so the user only needs to log in once).
    """

    site_name: str = ""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self.context: BrowserContext | None = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        profile_dir = str(get_browser_profile_dir() / self.site_name)
        self._browser = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-GB",
            timezone_id="Europe/London",
        )
        self.context = self._browser
        return self

    async def __aexit__(self, *args):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_page(self) -> Page:
        page = await self.context.new_page()
        # Remove automation fingerprint
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return page

    @staticmethod
    async def human_delay(min_ms: int = 800, max_ms: int = 2500) -> None:
        """Random delay to mimic human behaviour."""
        await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

    @abstractmethod
    async def scrape_jobs(
        self, queries: list[str], location: str, remote: bool = False
    ) -> list[dict[str, Any]]:
        """Return a list of job dicts with keys:
        title, company, location, url, site, description, salary, posted_date
        """
