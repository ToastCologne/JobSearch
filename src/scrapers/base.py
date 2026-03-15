"""Base scraper with persistent Playwright browser context."""
import asyncio
import random
from abc import ABC, abstractmethod
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

from src.config import get_browser_profile_dir

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_BROWSER_ARGS = ["--no-sandbox", "--disable-blink-features=AutomationControlled"]


class BaseScraper(ABC):
    """Base class for all job site scrapers."""

    site_name: str = ""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self.context: BrowserContext | None = None

    async def _open_context(self, headless: bool) -> None:
        """Launch (or relaunch) the persistent browser context."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        profile_dir = str(get_browser_profile_dir() / self.site_name)
        self._browser = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=headless,
            args=_BROWSER_ARGS,
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="en-GB",
            timezone_id="Europe/Luxembourg",
        )
        self.context = self._browser

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        await self._open_context(self.headless)
        return self

    async def __aexit__(self, *args):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_page(self) -> Page:
        page = await self.context.new_page()
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
