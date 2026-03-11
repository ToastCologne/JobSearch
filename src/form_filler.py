"""Playwright-based application form filler with AI field mapping."""
import asyncio
import base64
import json
from pathlib import Path

import anthropic
from playwright.async_api import async_playwright, Page

from src.config import get_anthropic_key, get_browser_profile_dir, get_output_dir
from src.cv_handler import extract_cv_text

MODEL = "claude-opus-4-6"

FIELD_MAPPING_PROMPT = """Analyse this job application form and the candidate's CV.
Return a JSON object mapping each fillable field to the appropriate value from the CV.

=== CANDIDATE CV ===
{cv_text}

=== FORM HTML (truncated) ===
{form_html}

Return JSON in this exact format — only include fields that exist in the form:
{{
  "fields": [
    {{
      "selector": "<CSS selector or label text>",
      "field_type": "text|email|phone|textarea|select|checkbox|radio",
      "value": "<value to fill>"
    }}
  ],
  "notes": "<any important observations about the form>"
}}"""


async def fill_application_form(
    job: dict,
    cv_path: Path,
    headless: bool = False,
) -> str | None:
    """
    Open the job application page, pre-fill the form, take a screenshot,
    and return the path to the screenshot.

    The browser stays open after filling so the user can review and submit.
    Returns the screenshot path, or None on failure.
    """
    cv_text = ""
    if cv_path.exists():
        cv_text = extract_cv_text(cv_path)

    profile_dir = str(get_browser_profile_dir() / "form_filler")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )

        page = await browser.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        job_url = job.get("url", "")
        if not job_url:
            await browser.close()
            return None

        try:
            await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # Look for an Apply button
            apply_btn = await _find_apply_button(page)
            if apply_btn:
                await apply_btn.click()
                await asyncio.sleep(2)

            # Get form HTML for AI analysis
            form_html = await _get_form_html(page)

            if form_html and cv_text:
                field_data = await _get_field_mapping(cv_text, form_html)
                await _fill_fields(page, field_data.get("fields", []))
                await asyncio.sleep(1)

            # Take screenshot
            screenshot_bytes = await page.screenshot(full_page=True)
            screenshot_path = get_output_dir("screenshots") / f"job_{job.get('id', 'unknown')}.png"
            screenshot_path.write_bytes(screenshot_bytes)

            # Keep browser open for user review
            print(f"\n[Form Filler] Form pre-filled. Screenshot saved to {screenshot_path}")
            print("[Form Filler] Browser is open for your review. Close it when done.")
            print("[Form Filler] DO NOT click Submit until you have reviewed all fields.")

            # Wait for browser to be closed by user
            try:
                await page.wait_for_event("close", timeout=300000)  # 5 min timeout
            except Exception:
                pass

            return str(screenshot_path)

        except Exception as e:
            print(f"[Form Filler] Error: {e}")
            return None
        finally:
            try:
                await browser.close()
            except Exception:
                pass


async def _find_apply_button(page: Page):
    """Try common Apply button selectors."""
    selectors = [
        "a:has-text('Apply Now')",
        "a:has-text('Apply')",
        "button:has-text('Apply Now')",
        "button:has-text('Apply')",
        "a:has-text('Easy Apply')",
        "[data-control-name='jobdetails_topcard_inapply']",
    ]
    for sel in selectors:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                return btn
        except Exception:
            continue
    return None


async def _get_form_html(page: Page) -> str:
    """Extract form HTML for AI analysis (capped at 8KB)."""
    try:
        form = await page.query_selector("form")
        if form:
            html = await form.inner_html()
            return html[:8000]
        return (await page.content())[:8000]
    except Exception:
        return ""


async def _get_field_mapping(cv_text: str, form_html: str) -> dict:
    """Ask Claude to map CV data to form fields."""
    client = anthropic.AsyncAnthropic(api_key=get_anthropic_key())

    prompt = FIELD_MAPPING_PROMPT.format(
        cv_text=cv_text[:3000],
        form_html=form_html,
    )

    response = await client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    text = next((b.text for b in response.content if b.type == "text"), "{}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"fields": []}


async def _fill_fields(page: Page, fields: list[dict]) -> None:
    """Fill form fields based on AI mapping."""
    for field in fields:
        selector = field.get("selector", "")
        value = field.get("value", "")
        field_type = field.get("field_type", "text")

        if not selector or not value:
            continue

        try:
            # Try CSS selector first, then label text
            el = await page.query_selector(selector)
            if not el:
                el = await page.query_selector(f"label:has-text('{selector}') + input")
            if not el:
                continue

            if field_type in ("text", "email", "phone"):
                await el.triple_click()
                await el.type(str(value), delay=50)
            elif field_type == "textarea":
                await el.triple_click()
                await el.type(str(value), delay=30)
            elif field_type == "select":
                await el.select_option(label=str(value))
            elif field_type == "checkbox" and str(value).lower() in ("true", "yes", "1"):
                if not await el.is_checked():
                    await el.click()

            await asyncio.sleep(0.2)

        except Exception as e:
            print(f"[Form Filler] Could not fill '{selector}': {e}")
