from __future__ import annotations

from typing import Callable

from updater.application.dto import ImportTargetsResult
from updater.domain.models import Target, TargetVersion
from updater.domain.repositories import TargetRepository, TargetVersionRepository


class ImportTargetsService:
    def __init__(
        self,
        target_repo: TargetRepository,
        version_repo: TargetVersionRepository,
        *,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.target_repo = target_repo
        self.version_repo = version_repo
        self._progress = progress or (lambda _: None)

    def import_items(self, items: list[tuple[Target, TargetVersion | None]]) -> ImportTargetsResult:
        result = ImportTargetsResult()
        self._progress(f"import_targets:start total={len(items)}")
        for target, version in items:
            self._progress(f"import_targets:target_upsert name={target.name}")
            saved_target = self.target_repo.upsert(target)
            result.targets_imported += 1
            if version is not None:
                version.target_id = saved_target.id
                self._progress(
                    f"import_targets:version_upsert target={target.name} version={version.version} type={version.version_type}"
                )
                self.version_repo.upsert(version)
                result.versions_imported += 1
        self._progress(
            f"import_targets:done targets_imported={result.targets_imported} versions_imported={result.versions_imported} errors={len(result.errors)}"
        )
        return result
