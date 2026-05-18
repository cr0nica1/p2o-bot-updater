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
        return {
            "targets": [_serialize(target) for target in self.target_repo.list_all()],
            "vulnerabilities": [_serialize(vulnerability) for vulnerability in self.vulnerability_repo.list_all()],
            "target_vulnerabilities": [_serialize(link) for link in self.target_vulnerability_repo.list_all()],
        }


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
