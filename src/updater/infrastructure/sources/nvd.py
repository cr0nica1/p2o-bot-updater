from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Callable

import requests

from updater.domain.models import Target, Vulnerability

NVD_CVES_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"


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
            entry = entries[0]
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

_NVD_METRIC_KEYS = ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2")


def strip_non_nist_cvss_metrics(item: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(item)
    cve = cleaned.get("cve", cleaned)
    metrics = cve.get("metrics")
    if not metrics:
        return cleaned
    for key in list(metrics.keys()):
        entries = metrics.get(key)
        if not isinstance(entries, list):
            continue
        nist_entries = [e for e in entries if e.get("source") in _NIST_SOURCES]
        if nist_entries:
            metrics[key] = nist_entries
        elif all("source" not in e for e in entries):
            metrics[key] = entries
        else:
            del metrics[key]
    return cleaned


class NvdSource:
    source_name: str = "nvd"

    def __init__(
        self,
        *,
        get: Callable[..., Any] | None = None,
        api_key: str | None = None,
    ) -> None:
        self._get = get or requests.get
        self._api_key = api_key

    def search(
        self, _target: Target, query: str, since_year: int | None = None
    ) -> list[tuple[Vulnerability, dict[str, Any]]]:
        params: dict[str, Any] = {"keywordSearch": query, "keywordExactMatch": ""}
        if since_year is not None:
            params["pubStartDate"] = f"{since_year}-01-01T00:00:00.000"
        headers = {"apiKey": self._api_key} if self._api_key else None

        response = self._get(NVD_CVES_URL, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()

        results: list[tuple[Vulnerability, dict[str, Any]]] = []
        for item in payload.get("vulnerabilities", []):
            cleaned = strip_non_nist_cvss_metrics(strip_cpe_from_raw(item))
            vulnerability = normalize_nvd_item(cleaned)
            evidence = {"query": query, "nvd": cleaned}
            results.append((vulnerability, evidence))
        return results
