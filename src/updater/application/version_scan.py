from __future__ import annotations

import logging
from dataclasses import dataclass

from updater.application.firmware_lookup import FirmwareLookupError
from updater.domain.models import Target, TargetVersion
from updater.infrastructure.browser import BrowserLaunchError, HttpFetchError

log = logging.getLogger("updater.version_scan")


@dataclass(frozen=True)
class VersionChange:
    target_name: str
    old_version: str
    new_version: str
    source_url: str


@dataclass(frozen=True)
class VersionScanReport:
    changes: list[VersionChange]
    seeded: list[str]
    unchanged: list[str]
    errors: list[tuple[str, str]]

    @property
    def scanned(self) -> int:
        return len(self.changes) + len(self.seeded) + len(self.unchanged)


class VersionScanService:
    def __init__(self, target_repo, vendor_config_repo, version_repo, lookup_service) -> None:
        self.target_repo = target_repo
        self.vendor_config_repo = vendor_config_repo
        self.version_repo = version_repo
        self.lookup_service = lookup_service

    def scan_all(self) -> VersionScanReport:
        changes: list[VersionChange] = []
        seeded: list[str] = []
        unchanged: list[str] = []
        errors: list[tuple[str, str]] = []

        targets = sorted(self.target_repo.list_all(), key=lambda t: t.name.casefold())
        for target_id, target in enumerate(targets, start=1):
            config = self.vendor_config_repo.find_by_target(target)
            if config is None:
                continue
            try:
                result = self.lookup_service.lookup(target_id)
            except (FirmwareLookupError, HttpFetchError, BrowserLaunchError) as exc:
                log.warning("version scan failed for %s: %s", target.name, exc)
                errors.append((target.name, str(exc)))
                continue

            storage_id = target.storage_id
            new_version = result.version
            current = self.version_repo.find_latest(storage_id)
            if current is None:
                self.version_repo.set_current(
                    storage_id, version=new_version,
                    source_url=result.resolved_url, previous_version=None,
                )
                seeded.append(target.name)
            elif current.version != new_version:
                self.version_repo.set_current(
                    storage_id, version=new_version,
                    source_url=result.resolved_url, previous_version=current.version,
                )
                changes.append(
                    VersionChange(target.name, current.version, new_version, result.resolved_url)
                )
            else:
                self.version_repo.mark_seen(storage_id, version=new_version)
                unchanged.append(target.name)

        return VersionScanReport(changes=changes, seeded=seeded, unchanged=unchanged, errors=errors)


def version_changes_from_docs(
    docs: list[TargetVersion], targets: list[Target]
) -> list[VersionChange]:
    names = {t.storage_id: t.name for t in targets}
    changes: list[VersionChange] = []
    for doc in docs:
        name = names.get(doc.target_id)
        if name is None:
            continue
        changes.append(
            VersionChange(name, doc.previous_version or "", doc.version or "", doc.source_url or "")
        )
    return changes
