from __future__ import annotations

import re
from typing import Callable

from updater.application.dto import SyncResult
from updater.domain.models import Target, TargetVulnerability, Vulnerability
from updater.domain.repositories import (
    TargetRepository,
    TargetVulnerabilityRepository,
    VulnerabilityRepository,
    VulnerabilitySource,
)


class SyncVulnerabilitiesService:
    def __init__(
        self,
        target_repo: TargetRepository,
        vulnerability_repo: VulnerabilityRepository,
        target_vulnerability_repo: TargetVulnerabilityRepository,
        sources: list[VulnerabilitySource],
        *,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.target_repo = target_repo
        self.vulnerability_repo = vulnerability_repo
        self.target_vulnerability_repo = target_vulnerability_repo
        self.sources = sources
        self._progress = progress or (lambda _: None)

    def sync_all(self) -> SyncResult:
        return self._sync_targets(self.target_repo.list_all(), use_since_years=True)

    def sync_one(self, target_name: str) -> SyncResult:
        target = self.target_repo.find_by_name(target_name)
        if target is None:
            return SyncResult()
        return self._sync_targets([target], use_since_years=False)

    def _sync_targets(self, targets: list[Target], *, use_since_years: bool) -> SyncResult:
        result = SyncResult()
        total_targets = len(targets)
        self._progress(f"sync:start total_targets={total_targets}")
        for index, target in enumerate(targets, start=1):
            before_vulnerabilities = result.vulnerabilities_seen
            before_links = result.links_updated
            before_errors = len(result.errors)
            self._progress(f"sync:target target={target.name} ({index}/{total_targets})")
            self._sync_target(target, result, use_since_years=use_since_years)
            result.targets_processed += 1
            self._progress(
                f"sync:target_done target={target.name} vulnerabilities={result.vulnerabilities_seen - before_vulnerabilities} links={result.links_updated - before_links} errors={len(result.errors) - before_errors}"
            )
        self._progress(
            f"sync:done targets_processed={result.targets_processed} vulnerabilities_seen={result.vulnerabilities_seen} links_updated={result.links_updated} errors={len(result.errors)}"
        )
        return result

    def _sync_target(self, target: Target, result: SyncResult, *, use_since_years: bool) -> None:
        since_years = self._compute_since_years(target) if use_since_years else {}
        for query in target.search_queries():
            for source in self.sources:
                try:
                    hits = source.search(
                        target, query, since_year=since_years.get(source.source_name)
                    )
                except Exception as exc:
                    result.errors.append(f"{source.source_name}:{target.name}:{query}:{exc}")
                    self._progress(f"sync:query_error source={source.source_name} query={query} error={exc}")
                    continue
                self._progress(f"sync:query source={source.source_name} query={query} hits={len(hits)}")
                for vulnerability, evidence in hits:
                    saved_vuln = self.vulnerability_repo.upsert(vulnerability)
                    result.vulnerabilities_seen += 1
                    link = TargetVulnerability(
                        target_id=target.id or target.normalized_name,
                        target_name=target.name,
                        vulnerability_id=saved_vuln.id or saved_vuln.advisory_id,
                    )
                    link.add_evidence(
                        source=source.source_name,
                        matched_query=query,
                        evidence=evidence,
                    )
                    self.target_vulnerability_repo.upsert(link)
                    result.links_updated += 1

    def _compute_since_years(self, target: Target) -> dict[str, int]:
        target_id = target.id or target.normalized_name
        vulnerabilities = self.vulnerability_repo.list_all()
        vulnerabilities_by_id: dict[str, Vulnerability] = {}
        for vulnerability in vulnerabilities:
            if vulnerability.id:
                vulnerabilities_by_id[vulnerability.id] = vulnerability
            vulnerabilities_by_id[vulnerability.advisory_id] = vulnerability

        cve_years: list[int] = []
        zdi_years: list[int] = []
        for link in self.target_vulnerability_repo.list_all():
            if link.target_id != target_id:
                continue
            vulnerability = vulnerabilities_by_id.get(link.vulnerability_id)
            if vulnerability is None:
                continue
            cve_years.extend(_cve_years_from_vulnerability(vulnerability))
            zdi_years.extend(_zdi_years_from_vulnerability(vulnerability))

        result: dict[str, int] = {}
        if cve_years:
            result["nvd"] = max(cve_years)
        if zdi_years:
            result["zdi"] = max(zdi_years)
        return result


_CVE_YEAR_RE = re.compile(r"\bCVE-(\d{4})-\d{4,7}\b", re.IGNORECASE)
_ZDI_YEAR_RE = re.compile(r"\bZDI-(?:CAN-)?(\d{2,4})-\d{3,7}\b", re.IGNORECASE)


def _cve_years_from_vulnerability(vulnerability: Vulnerability) -> list[int]:
    values = [vulnerability.advisory_id, *vulnerability.aliases]
    return [int(match.group(1)) for value in values for match in _CVE_YEAR_RE.finditer(value)]


def _zdi_years_from_vulnerability(vulnerability: Vulnerability) -> list[int]:
    values = [vulnerability.advisory_id, *vulnerability.aliases]
    zdi_raw = vulnerability.raw.get("zdi")
    if isinstance(zdi_raw, dict):
        zdi_id = zdi_raw.get("zdi_id")
        if isinstance(zdi_id, str):
            values.append(zdi_id)
    years = [_normalize_zdi_year(match.group(1)) for value in values for match in _ZDI_YEAR_RE.finditer(value)]
    if "zdi" in vulnerability.sources and vulnerability.published_date is not None:
        years.append(vulnerability.published_date.year)
    return years


def _normalize_zdi_year(value: str) -> int:
    year = int(value)
    if year < 100:
        return 2000 + year
    return year
