from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from updater.domain.repositories import TargetRepository, TargetVulnerabilityRepository, VulnerabilityRepository


class ExportService:
    def __init__(
        self,
        target_repo: TargetRepository,
        vulnerability_repo: VulnerabilityRepository,
        target_vulnerability_repo: TargetVulnerabilityRepository,
    ) -> None:
        self.target_repo = target_repo
        self.vulnerability_repo = vulnerability_repo
        self.target_vulnerability_repo = target_vulnerability_repo

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        vulnerabilities_by_id = _vulnerabilities_by_id(self.vulnerability_repo.list_all())
        links = self.target_vulnerability_repo.list_all()

        grouped: dict[str, dict[str, Any]] = {}
        for link in links:
            serialized = _serialize(link)
            vuln_id = serialized.get("vulnerability_id")
            vuln = vulnerabilities_by_id.get(vuln_id) if vuln_id else None

            target_entry = _build_target_entry(serialized)

            if vuln_id not in grouped:
                entry: dict[str, Any] = {}
                if vuln is not None:
                    entry = _serialize(vuln)
                entry["affected_targets"] = [target_entry]
                grouped[vuln_id] = entry
            else:
                _merge_target_entry(grouped[vuln_id], target_entry)

        return {"target_vulnerabilities": list(grouped.values())}


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    if hasattr(value, "__dict__"):
        return {key: _serialize(item) for key, item in vars(value).items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def _vulnerabilities_by_id(vulnerabilities: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for vuln in vulnerabilities:
        key = vuln.id or vuln.advisory_id
        result[key] = vuln
    return result


def _build_target_entry(link: dict[str, Any]) -> dict[str, Any]:
    _strip_query_fields(link)
    link.pop("id", None)
    link.pop("vulnerability_id", None)
    return link


def _merge_target_entry(entry: dict[str, Any], target_entry: dict[str, Any]) -> None:
    affected_targets = entry["affected_targets"]
    existing = next(
        (
            target
            for target in affected_targets
            if target.get("target_id") == target_entry.get("target_id")
        ),
        None,
    )
    if existing is None:
        affected_targets.append(target_entry)
        return

    existing["affected_versions"] = _unique([*existing.get("affected_versions", []), *target_entry.get("affected_versions", [])])
    existing["fixed_versions"] = _unique([*existing.get("fixed_versions", []), *target_entry.get("fixed_versions", [])])
    existing["evidence_sources"] = [*existing.get("evidence_sources", []), *target_entry.get("evidence_sources", [])]
    if target_entry.get("first_seen_at") and target_entry["first_seen_at"] < existing.get("first_seen_at", target_entry["first_seen_at"]):
        existing["first_seen_at"] = target_entry["first_seen_at"]
    if target_entry.get("last_seen_at") and target_entry["last_seen_at"] > existing.get("last_seen_at", target_entry["last_seen_at"]):
        existing["last_seen_at"] = target_entry["last_seen_at"]


def _unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _strip_query_fields(link: dict[str, Any]) -> dict[str, Any]:
    link.pop("matched_queries", None)
    for source in link.get("evidence_sources", []):
        evidence = source.get("evidence", {})
        evidence.pop("query", None)
    return link
