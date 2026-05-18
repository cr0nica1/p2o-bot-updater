from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

import requests

from updater.domain.models import Target, Vulnerability

NVD_CVES_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def normalize_nvd_item(item: dict[str, Any]) -> Vulnerability:
    cve = item.get("cve", item)
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

    # --- references ---
    references: list[str] = [
        ref.get("url")
        for ref in cve.get("references", {}).get("referenceData", [])
        if ref.get("url")
    ]

    # --- CVSS metrics (try v3.1, then v3.0, then v2) ---
    cvss_score: float | None = None
    severity: str | None = None
    metrics = cve.get("metrics", {})
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key)
        if entries:
            data = entries[0].get("cvssData", {})
            cvss_score = data.get("baseScore")
            sev = data.get("baseSeverity")
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
        raw=item,
    )


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
        self, target: Target, query: str
    ) -> list[tuple[Vulnerability, dict[str, Any]]]:
        params: dict[str, Any] = {"keywordSearch": query}
        if self._api_key:
            params["apiKey"] = self._api_key

        response = self._get(NVD_CVES_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()

        results: list[tuple[Vulnerability, dict[str, Any]]] = []
        for item in payload.get("vulnerabilities", []):
            vulnerability = normalize_nvd_item(item)
            evidence = {"query": query, "nvd": item}
            results.append((vulnerability, evidence))
        return results
