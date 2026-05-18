from __future__ import annotations

from updater.application.dto import ImportTargetsResult
from updater.domain.models import Target, TargetVersion
from updater.domain.repositories import TargetRepository, TargetVersionRepository


class ImportTargetsService:
    def __init__(
        self,
        target_repo: TargetRepository,
        version_repo: TargetVersionRepository,
    ) -> None:
        self.target_repo = target_repo
        self.version_repo = version_repo

    def import_items(self, items: list[tuple[Target, TargetVersion | None]]) -> ImportTargetsResult:
        result = ImportTargetsResult()
        for target, version in items:
            saved_target = self.target_repo.upsert(target)
            result.targets_imported += 1
            if version is not None:
                version.target_id = saved_target.id
                self.version_repo.upsert(version)
                result.versions_imported += 1
        return result
