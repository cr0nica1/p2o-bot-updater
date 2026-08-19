from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from updater.domain.models import Target, TargetVersion


KNOWN_COLUMNS = {
    "name",
    "aliases",
    "search_names",
    "vendor",
    "vendor_alias",
    "category",
    "version",
    "version_type",
    "release_date",
    "source_url",
}


@dataclass
class LoadedTarget:
    target: Target
    version: TargetVersion | None


@dataclass
class CsvLoadResult:
    items: list[LoadedTarget] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class CsvTargetLoader:
    def load(self, path: Path) -> CsvLoadResult:
        result = CsvLoadResult()

        with path.open(newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            for row_number, row in enumerate(reader, start=2):
                name = _clean_optional(row.get("name"))
                if name is None:
                    result.errors.append(f"row {row_number}: missing required name")
                    continue

                target = Target(
                    name=name,
                    aliases=_split_aliases(row.get("aliases")),
                    search_names=_split_aliases(row.get("search_names")),
                    vendor=_clean_optional(row.get("vendor")),
                    vendor_alias=_clean_optional(row.get("vendor_alias")),
                    category=_clean_optional(row.get("category")),
                    raw_metadata=_unknown_metadata(row),
                )
                result.items.append(
                    LoadedTarget(
                        target=target,
                        version=_version_from_row(row),
                    )
                )

        return result


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _split_aliases(value: str | None) -> list[str]:
    if value is None:
        return []
    return [alias.strip() for alias in value.split(";") if alias.strip()]


def _unknown_metadata(row: dict[str, str | None]) -> dict[str, str]:
    return {
        column: value.strip()
        for column, value in row.items()
        if column
        and column not in KNOWN_COLUMNS
        and isinstance(value, str)
        and value.strip()
    }


def _version_from_row(row: dict[str, str | None]) -> TargetVersion | None:
    version = _clean_optional(row.get("version"))
    if version is None:
        return None

    return TargetVersion(
        version=version,
        version_type=_clean_optional(row.get("version_type")),
        release_date=_parse_release_date(row.get("release_date")),
        source_url=_clean_optional(row.get("source_url")),
    )


def _parse_release_date(value: str | None) -> datetime | None:
    cleaned = _clean_optional(value)
    if cleaned is None:
        return None

    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
