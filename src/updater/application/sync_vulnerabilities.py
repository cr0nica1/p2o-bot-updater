from __future__ import annotations

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
    ) -> None:
        self.target_repo = target_repo
        self.vulnerability_repo = vulnerability_repo
        self.target_vulnerability_repo = target_vulnerability_repo
        self.sources = sources

    def sync_all(self) -> SyncResult:
        return self._sync_targets(self.target_repo.list_all())

    def sync_one(self, target_name: str) -> SyncResult:
        target = self.target_repo.find_by_name(target_name)
        if target is None:
            return SyncResult()
        return self._sync_targets([target])

    def _sync_targets(self, targets: list[Target]) -> SyncResult:
        result = SyncResult()
        for target in targets:
            self._sync_target(target, result)
            result.targets_processed += 1
        return result

    def _sync_target(self, target: Target, result: SyncResult) -> None:
        for query in target.search_queries():
            for source in self.sources:
                try:
                    hits = source.search(target, query)
                except Exception as exc:
                    result.errors.append(f"{source.source_name}:{target.name}:{query}:{exc}")
                    continue
                for vulnerability, evidence in hits:
                    saved_vuln = self.vulnerability_repo.upsert(vulnerability)
                    result.vulnerabilities_seen += 1
                    link = TargetVulnerability(
                        target_id=target.id or target.normalized_name,
                        vulnerability_id=saved_vuln.id or saved_vuln.advisory_id,
                    )
                    link.add_evidence(
                        source=source.source_name,
                        matched_query=query,
                        evidence=evidence,
                    )
                    self.target_vulnerability_repo.upsert(link)
                    result.links_updated += 1
