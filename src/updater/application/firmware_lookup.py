from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, urljoin, urlparse

from updater.domain.models import Target, VendorConfig
from updater.domain.repositories import TargetRepository, VendorConfigRepository


class FirmwareLookupError(Exception):
    pass


class BrowserAdapter(Protocol):
    def fetch_element_html(self, url: str, element_id: str) -> str: ...


@dataclass(frozen=True)
class FirmwareLookupResult:
    target_name: str
    vendor: str
    resolved_url: str
    version: str
    download_url: str
    html_snippet: str


def _sorted_targets(targets: list[Target]) -> list[Target]:
    return sorted(targets, key=lambda target: target.name.casefold())


def validate_vendor_config(config: VendorConfig) -> None:
    parsed = urlparse(config.url_template)
    if parsed.scheme != "https":
        raise FirmwareLookupError("Vendor URL template must use HTTPS")
    if "{alias}" not in config.url_template:
        raise FirmwareLookupError("Vendor URL template must contain {alias}")
    try:
        compiled = re.compile(config.regex, re.DOTALL)
    except re.error as exc:
        raise FirmwareLookupError(f"Vendor regex is invalid: {exc}") from exc
    if compiled.groups < 2:
        raise FirmwareLookupError("Vendor regex must have at least two capture groups")


def _render_url(template: str, vendor_alias: str) -> str:
    return template.replace("{alias}", quote(vendor_alias, safe=""))


def _resolve_download_url(page_url: str, captured_url: str) -> str:
    resolved = urljoin(page_url, captured_url.strip())
    parsed = urlparse(resolved)
    if parsed.scheme != "https":
        raise FirmwareLookupError("Captured download URL must be relative or HTTPS")
    return resolved


class FirmwareLookupService:
    def __init__(
        self,
        target_repo: TargetRepository,
        vendor_config_repo: VendorConfigRepository,
        browser: BrowserAdapter,
    ) -> None:
        self.target_repo = target_repo
        self.vendor_config_repo = vendor_config_repo
        self.browser = browser

    def lookup(self, target_id: int) -> FirmwareLookupResult:
        targets = _sorted_targets(self.target_repo.list_all())
        if target_id < 1 or target_id > len(targets):
            raise FirmwareLookupError(f"Invalid target ID. Use /list-targets to see available targets (1-{len(targets)}).")

        target = targets[target_id - 1]
        if not target.vendor:
            raise FirmwareLookupError(f"Target {target.name!r} has no vendor. Set vendor before firmware lookup.")
        if not target.vendor_alias:
            raise FirmwareLookupError(f"Target {target.name!r} has no vendor_alias. Set vendor_alias before firmware lookup.")

        config = self.vendor_config_repo.find_by_vendor(target.vendor)
        if config is None:
            raise FirmwareLookupError(f"No firmware vendor config found for {target.vendor}.")
        validate_vendor_config(config)

        resolved_url = _render_url(config.url_template, target.vendor_alias)
        html = self.browser.fetch_element_html(resolved_url, config.attr_id)
        match = re.search(config.regex, html, re.DOTALL)
        if match is None:
            raise FirmwareLookupError(f"Regex did not match element #{config.attr_id} at {resolved_url}.")

        version = match.group(1).strip()
        download_url = _resolve_download_url(resolved_url, match.group(2))
        return FirmwareLookupResult(
            target_name=target.name,
            vendor=target.vendor,
            resolved_url=resolved_url,
            version=version,
            download_url=download_url,
            html_snippet=html,
        )
