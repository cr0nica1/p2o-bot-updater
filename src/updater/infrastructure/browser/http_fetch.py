from __future__ import annotations

from typing import Any, Callable

import requests
from bs4 import BeautifulSoup


class HttpFetchError(Exception):
    pass


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class HttpFetchAdapter:
    def __init__(
        self,
        *,
        timeout: int = 30,
        user_agent: str = DEFAULT_USER_AGENT,
        get: Callable[..., Any] | None = None,
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent
        self._get = get or requests.get

    def fetch_html(self, url: str, selector: str | None = None) -> str:
        try:
            response = self._get(
                url, headers={"User-Agent": self.user_agent}, timeout=self.timeout
            )
            response.raise_for_status()
        except Exception as exc:
            raise HttpFetchError(f"HTTP fetch failed for {url}: {exc}") from exc

        text = response.text
        if not selector:
            return text
        soup = BeautifulSoup(text, "html.parser")
        element = soup.select_one(selector)
        if element is None:
            raise HttpFetchError(f"Selector {selector!r} not found at {url}.")
        return str(element)
