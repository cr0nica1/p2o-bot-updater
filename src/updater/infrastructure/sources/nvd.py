from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any

import requests

from updater.domain.models import Target, Vulnerability

NVD_CVES_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
NVD_WINDOW_DAYS = 119


def nvd_pub_windows(since_year: int, *, today: date | None = None) -> list[tuple[str, str]]:
    today = today or date.today()
    start = date(since_year, 1, 1)
    if start > today:
        return []
    windows: list[tuple[str, str]] = []
    cursor = start
    while cursor <= today:
        end = min(cursor + timedelta(days=NVD_WINDOW_DAYS), today)
        windows.append(
            (f"{cursor.isoformat()}T00:00:00.000", f"{end.isoformat()}T23:59:59.999")
        )
        cursor = end + timedelta(days=1)
    return windows


def normalize_nvd_item(item: dict[str, Any]) -> Vulnerability:
    cleaned = strip_non_english_descriptions(strip_non_nist_cvss_metrics(strip_cpe_from_raw(item)))
    cve = cleaned.get("cve", cleaned)
    cve_id: str = cve.get("id", "")

    # --- published date ---
    published_raw: str | None = cve.get("published")
    published_date: datetime | None = None
    if published_raw:
        published_date = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))

    # --- description (English) ---
    description: str | None = None
    for desc in cve.get("descriptions", []):
        if desc.get("lang") == "en":
            description = desc.get("value")
            break

    # --- references (NVD API 2.0 list or legacy referenceData dict) ---
    raw_refs = cve.get("references", [])
    if isinstance(raw_refs, list):
        references: list[str] = [
            ref.get("url") for ref in raw_refs if ref.get("url")
        ]
    else:
        references: list[str] = [
            ref.get("url")
            for ref in raw_refs.get("referenceData", [])
            if ref.get("url")
        ]

    # --- CVSS metrics (try v3.1, then v3.0, then v2) ---
    cvss_score: float | None = None
    severity: str | None = None
    metrics = cve.get("metrics", {})
    for key in _NVD_METRIC_KEYS:
        entries = metrics.get(key)
        if entries:
            entry = _preferred_metric_entry(entries)
            data = entry.get("cvssData", {})
            cvss_score = data.get("baseScore")
            sev = data.get("baseSeverity") or entry.get("baseSeverity")
            if sev:
                severity = sev.lower()
            break

    return Vulnerability.from_source(
        source="nvd",
        advisory_id=cve_id,
        cve_id=cve_id,
        cvss_score=cvss_score,
        severity=severity,
        description=description,
        references=references,
        published_date=published_date,
        raw=cleaned,
    )


def strip_cpe_from_raw(item: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(item)
    cve = cleaned.get("cve", cleaned)
    cve.pop("configurations", None)
    return cleaned


def strip_non_english_descriptions(item: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(item)
    cve = cleaned.get("cve", cleaned)
    descriptions = cve.get("descriptions")
    if isinstance(descriptions, list):
        cve["descriptions"] = [d for d in descriptions if d.get("lang") == "en"]
    return cleaned


_NIST_SOURCES = {"nvd@nist.gov"}

_NVD_METRIC_KEYS = ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2")


def _preferred_metric_entry(entries: list[dict[str, Any]]) -> dict[str, Any]:
    for entry in entries:
        if entry.get("source") in _NIST_SOURCES:
            return entry
    return entries[0]


def strip_non_nist_cvss_metrics(item: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(item)
    cve = cleaned.get("cve", cleaned)
    metrics = cve.get("metrics")
    if not metrics:
        return cleaned

    has_nist = any(
        entry.get("source") in _NIST_SOURCES
        for entries in metrics.values()
        if isinstance(entries, list)
        for entry in entries
    )

    for key in list(metrics.keys()):
        entries = metrics.get(key)
        if not isinstance(entries, list):
            continue
        nist_entries = [e for e in entries if e.get("source") in _NIST_SOURCES]
        if nist_entries:
            metrics[key] = nist_entries
        elif all("source" not in e for e in entries):
            metrics[key] = entries
        elif not has_nist:
            # NIST has not scored this CVE anywhere; fall back to the
            # CNA-provided metrics so severity/CVSS are not lost as N/A.
            metrics[key] = entries
        else:
            del metrics[key]
    return cleaned


class NvdSource:
    source_name: str = "nvd"

    def __init__(self, *, get=None, api_key=None, pause=None):
        self._get = get or requests.get
        self._api_key = api_key
        if pause is not None:
            self._pause = pause
        elif get is None:
            import time
            self._pause = time.sleep
        else:
            self._pause = None

    def search(
        self,
        _target: Target,
        query: str,
        since_year: int | None = None,
        *,
        today: date | None = None,
    ) -> list[tuple[Vulnerability, dict[str, Any]]]:
        base: dict[str, Any] = {"keywordSearch": query, "keywordExactMatch": ""}
        headers = {"apiKey": self._api_key} if self._api_key else None
        windows = nvd_pub_windows(since_year, today=today) if since_year is not None else [None]
        results: list[tuple[Vulnerability, dict[str, Any]]] = []
        for index, window in enumerate(windows):
            if index and self._pause:
                self._pause(0.6 if self._api_key else 6.0)
            params = dict(base)
            if window is not None:
                params["pubStartDate"], params["pubEndDate"] = window
            results.extend(self._hits(params, headers, query))
        return results

    def _hits(self, params, headers, query):
        response = self._get(NVD_CVES_URL, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        results = []
        for item in payload.get("vulnerabilities", []):
            cleaned = strip_non_nist_cvss_metrics(strip_cpe_from_raw(item))
            vulnerability = normalize_nvd_item(cleaned)
            results.append((vulnerability, {"query": query, "nvd": cleaned}))
        return results
