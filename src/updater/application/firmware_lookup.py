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


class FetchAdapter(Protocol):
    def fetch_html(self, url: str, selector: str | None = None) -> str: ...


@dataclass(frozen=True)
class FirmwareLookupResult:
    target_name: str
    vendor: str
    resolved_url: str
    version: str
    download_url: str | None
    html_snippet: str


def _sorted_targets(targets: list[Target]) -> list[Target]:
    return sorted(targets, key=lambda target: target.name.casefold())


def validate_vendor_inputs(url_template: str, regex: str) -> None:
    parsed = urlparse(url_template)
    if parsed.scheme != "https":
        raise FirmwareLookupError("Vendor URL template must use HTTPS")
    try:
        compiled = re.compile(regex, re.DOTALL)
    except re.error as exc:
        raise FirmwareLookupError(f"Vendor regex is invalid: {exc}") from exc
    if compiled.groups < 1:
        raise FirmwareLookupError("Vendor regex must have at least one capture group")


def validate_vendor_config(config: VendorConfig) -> None:
    validate_vendor_inputs(config.url_template, config.regex)
    if config.fetch not in ("browser", "http"):
        raise FirmwareLookupError("Vendor config fetch must be 'browser' or 'http'")
    if config.select not in ("first", "last", "max"):
        raise FirmwareLookupError("Vendor config select must be 'first', 'last', or 'max'")


def _render_url(template: str, vendor_alias: str) -> str:
    return template.replace("{alias}", quote(vendor_alias, safe="/"))


def _version_key(value: str | None) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value or ""))


def _select_match(regex: str, html: str, select: str):
    matches = list(re.finditer(regex, html, re.DOTALL))
    if not matches:
        return None
    if select == "last":
        return matches[-1]
    if select == "max":
        return max(matches, key=lambda m: _version_key(m.group(1)))
    return matches[0]


def _resolve_download_url(page_url: str, captured_url: str) -> str:
    resolved = urljoin(page_url, captured_url.strip())
    parsed = urlparse(resolved)
    if parsed.scheme != "https":
        raise FirmwareLookupError("Captured download URL must be relative or HTTPS")
    return parsed._replace(path=quote(parsed.path, safe="/:%@!$&'()*+,;=-")).geturl()


class FirmwareLookupService:
    def __init__(
        self,
        target_repo: TargetRepository,
        vendor_config_repo: VendorConfigRepository,
        browser: BrowserAdapter,
        http: "FetchAdapter | None" = None,
    ) -> None:
        self.target_repo = target_repo
        self.vendor_config_repo = vendor_config_repo
        self.browser = browser
        self.http = http

    def lookup(self, target_id: int) -> FirmwareLookupResult:
        target = self._target_by_id(target_id)

        bound = self.vendor_config_repo.find_by_target(target)
        if bound is not None:
            validate_vendor_config(bound)
            if "{alias}" in bound.url_template and not target.vendor_alias:
                raise FirmwareLookupError(
                    f"Target {target.name!r} has no vendor_alias. Set vendor_alias before version lookup."
                )
            return self._lookup_target(target=target, config=bound)

        if not target.vendor:
            raise FirmwareLookupError(
                f"Target {target.name!r} has no vendor. Set vendor before firmware lookup."
            )
        if not target.vendor_alias:
            raise FirmwareLookupError(
                f"Target {target.name!r} has no vendor_alias. Set vendor_alias before firmware lookup."
            )
        config = self.vendor_config_repo.find_by_vendor(target.vendor)
        if config is None:
            raise FirmwareLookupError(f"No firmware vendor config found for {target.vendor}.")
        validate_vendor_config(config)
        return self._lookup_target(target=target, config=config)

    def lookup_with_inputs(
        self, *, target_id: int, url_template: str, attr_id: str, regex: str
    ) -> FirmwareLookupResult:
        target = self._target_by_id(target_id)
        if "{alias}" in url_template and not target.vendor_alias:
            raise FirmwareLookupError(
                f"Target {target.name!r} has no vendor_alias. Set vendor_alias before version lookup."
            )
        validate_vendor_inputs(url_template, regex)
        config = VendorConfig(
            vendor=target.vendor or target.name,
            url_template=url_template,
            attr_id=attr_id,
            regex=regex,
            fetch="browser",
            select="first",
        )
        return self._lookup_target(target=target, config=config)

    def _target_by_id(self, target_id: int) -> Target:
        targets = _sorted_targets(self.target_repo.list_all())
        if target_id < 1 or target_id > len(targets):
            raise FirmwareLookupError(
                f"Invalid target ID. Use /list-targets to see available targets (1-{len(targets)})."
            )
        return targets[target_id - 1]

    def _lookup_target(self, *, target: Target, config: VendorConfig) -> FirmwareLookupResult:
        resolved_url = _render_url(config.url_template, target.vendor_alias or "")
        if config.fetch == "http":
            if self.http is None:
                raise FirmwareLookupError("HTTP fetch adapter is not configured for this lookup.")
            html = self.http.fetch_html(resolved_url, config.selector)
        else:
            html = self.browser.fetch_element_html(resolved_url, config.attr_id)

        match = _select_match(config.regex, html, config.select)
        if match is None:
            location = config.selector or (f"#{config.attr_id}" if config.attr_id else "page")
            raise FirmwareLookupError(f"Regex did not match {location} at {resolved_url}.")

        version = match.group(1).strip()
        download_url: str | None = None
        if match.re.groups >= 2 and match.group(2):
            download_url = _resolve_download_url(resolved_url, match.group(2))

        return FirmwareLookupResult(
            target_name=target.name,
            vendor=target.vendor or config.vendor or "",
            resolved_url=resolved_url,
            version=version,
            download_url=download_url,
            html_snippet=html,
        )
