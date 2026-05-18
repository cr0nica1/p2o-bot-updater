from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests

from updater.domain.models import Target, Vulnerability

ZDI_BASE_URL = "https://www.zerodayinitiative.com"
ZDI_ADVISORIES_URL = f"{ZDI_BASE_URL}/advisories/"

_ZDI_ID_RE = re.compile(r"\bZDI-(?:CAN-)?\d{2,5}-\d{3,5}\b|\bZDI-CAN-\d{4,7}\b", re.IGNORECASE)
_CVE_ID_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
_CVSS_RE = re.compile(r"\bCVSS(?:\s+(?:Score|v3(?:\.\d)?))?\s*:?\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE)
_SEVERITY_RE = re.compile(r"\b(Critical|High|Medium|Low|Informational)\b", re.IGNORECASE)
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|[A-Z][a-z]+\s+\d{1,2},\s+\d{4})\b")


def parse_zdi_search_results(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "/advisories/" not in href or not _ZDI_ID_RE.search(href):
            continue

        detail_url = urljoin(ZDI_BASE_URL, href)
        if detail_url not in seen:
            seen.add(detail_url)
            links.append(detail_url)

    return links


def parse_zdi_detail(html: str, detail_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    zdi_match = _ZDI_ID_RE.search(text) or _ZDI_ID_RE.search(detail_url)
    cve_match = _CVE_ID_RE.search(text)
    cvss_match = _CVSS_RE.search(text)
    severity = _extract_labeled_value(text, "severity") or _extract_severity(text)
    published_date = _extract_labeled_value(text, "published") or _extract_labeled_value(text, "date") or _extract_date(text)
    description = _extract_description(soup, text)
    references = _extract_references(soup, detail_url)

    return {
        "zdi_id": zdi_match.group(0).upper() if zdi_match else None,
        "cve_id": cve_match.group(0).upper() if cve_match else None,
        "cvss_score": float(cvss_match.group(1)) if cvss_match else None,
        "severity": severity,
        "description": description,
        "references": references,
        "published_date": published_date,
        "detail_url": detail_url,
    }


def normalize_zdi_advisory(raw: dict[str, Any]) -> Vulnerability:
    published_date = _parse_date(raw.get("published_date"))
    severity = raw.get("severity")

    return Vulnerability.from_source(
        source="zdi",
        advisory_id=raw.get("zdi_id") or raw.get("cve_id") or "",
        cve_id=raw.get("cve_id"),
        cvss_score=raw.get("cvss_score"),
        severity=severity.lower() if isinstance(severity, str) else None,
        description=raw.get("description"),
        references=raw.get("references", []),
        published_date=published_date,
        raw=raw,
    )


class ZdiSource:
    source_name: str = "zdi"

    def __init__(self, *, get: Callable[..., Any] | None = None) -> None:
        self._get = get or requests.get

    def search(
        self, _target: Target, query: str
    ) -> list[tuple[Vulnerability, dict[str, Any]]]:
        response = self._get(ZDI_ADVISORIES_URL, params={"q": query}, timeout=30)
        response.raise_for_status()

        results: list[tuple[Vulnerability, dict[str, Any]]] = []
        for detail_url in parse_zdi_search_results(response.text):
            detail_response = self._get(detail_url, timeout=30)
            detail_response.raise_for_status()
            raw = parse_zdi_detail(detail_response.text, detail_url)
            vulnerability = normalize_zdi_advisory(raw)
            evidence = {"query": query, "url": detail_url, "zdi": raw}
            results.append((vulnerability, evidence))

        return results


def _extract_labeled_value(text: str, label: str) -> str | None:
    pattern = re.compile(rf"\b{re.escape(label)}\b\s*:?\s*([^\n]+)", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _extract_severity(text: str) -> str | None:
    match = _SEVERITY_RE.search(text)
    return match.group(1) if match else None


def _extract_date(text: str) -> str | None:
    match = _DATE_RE.search(text)
    return match.group(1) if match else None


def _extract_description(soup: BeautifulSoup, text: str) -> str | None:
    for selector in ("meta[name='description']", "meta[property='og:description']"):
        tag = soup.select_one(selector)
        if tag and tag.get("content"):
            return str(tag["content"]).strip()

    description = _extract_labeled_value(text, "description")
    if description:
        return description

    paragraphs = [paragraph.get_text(" ", strip=True) for paragraph in soup.find_all("p")]
    return next((paragraph for paragraph in paragraphs if paragraph), None)


def _extract_references(soup: BeautifulSoup, detail_url: str) -> list[str]:
    references = [
        urljoin(ZDI_BASE_URL, anchor["href"])
        for anchor in soup.find_all("a", href=True)
        if anchor["href"].startswith(("http://", "https://"))
    ]
    return _unique([detail_url, *references])


def _parse_date(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None

    cleaned = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        return None


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result
