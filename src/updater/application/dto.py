from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImportTargetsResult:
    targets_imported: int = 0
    versions_imported: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class SyncResult:
    targets_processed: int = 0
    vulnerabilities_seen: int = 0
    links_updated: int = 0
    errors: list[str] = field(default_factory=list)
