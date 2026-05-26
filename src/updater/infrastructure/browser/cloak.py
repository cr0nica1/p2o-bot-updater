from __future__ import annotations

from importlib import import_module
from typing import Any


class BrowserLaunchError(Exception):
    pass


class CloakBrowserAdapter:
    def __init__(self, *, timeout_ms: int = 30_000, headless: bool = True) -> None:
        self.timeout_ms = timeout_ms
        self.headless = headless

    def fetch_element_html(self, url: str, element_id: str) -> str:
        try:
            playwright_api = import_module("playwright.sync_api")
        except ModuleNotFoundError as exc:
            raise BrowserLaunchError(
                "playwright is required for firmware lookup; install dependencies and run `playwright install chromium`."
            ) from exc

        playwright = playwright_api.sync_playwright().start()
        browser: Any | None = None
        context: Any | None = None
        try:
            browser = playwright.chromium.launch(headless=self.headless)
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            locator = page.locator(f"#{element_id}")
            if locator.count() == 0:
                raise BrowserLaunchError(f"Element #{element_id} not found at {url}.")
            html = locator.first.inner_html(timeout=self.timeout_ms)
            wait_for_timeout = getattr(page, "wait_for_timeout", None)
            if wait_for_timeout is not None:
                for _ in range(4):
                    wait_for_timeout(500)
                    html = locator.first.inner_html(timeout=self.timeout_ms)
            return html
        except BrowserLaunchError:
            raise
        except Exception as exc:
            raise BrowserLaunchError(f"Browser lookup failed for {url}: {exc}") from exc
        finally:
            if context is not None:
                context.close()
            if browser is not None:
                browser.close()
            playwright.stop()
