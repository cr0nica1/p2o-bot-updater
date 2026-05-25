from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import re


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        key = normalize_name(cleaned) if cleaned else ""
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


@dataclass
class Target:
    name: str
    aliases: list[str] = field(default_factory=list)
    vendor: str | None = None
    vendor_alias: str | None = None
    category: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def normalized_name(self) -> str:
        return normalize_name(self.name)

    def search_queries(self) -> list[str]:
        return _unique_non_empty([self.name, *self.aliases])


@dataclass
class TargetVersion:
    target_id: str | None = None
    version: str | None = None
    version_type: str | None = None
    release_date: datetime | None = None
    source_url: str | None = None
    is_latest: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    first_seen_at: datetime = field(default_factory=utc_now)
    last_seen_at: datetime = field(default_factory=utc_now)


@dataclass
class VendorConfig:
    vendor: str
    url_template: str
    attr_id: str
    regex: str
    id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def normalized_vendor(self) -> str:
        return normalize_name(self.vendor)


@dataclass
class Vulnerability:
    advisory_id: str
    aliases: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    cvss_score: float | None = None
    severity: str | None = None
    description: str | None = None
    references: list[str] = field(default_factory=list)
    published_date: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @classmethod
    def from_source(
        cls,
        *,
        source: str,
        advisory_id: str,
        cve_id: str | None,
        cvss_score: float | None,
        severity: str | None,
        description: str | None,
        references: list[str],
        published_date: datetime | None,
        raw: dict[str, Any],
    ) -> "Vulnerability":
        canonical_id = cve_id or advisory_id
        aliases = _unique_non_empty([] if canonical_id == advisory_id else [advisory_id])
        return cls(
            advisory_id=canonical_id,
            aliases=aliases,
            sources=[source],
            cvss_score=cvss_score,
            severity=severity,
            description=description,
            references=_unique_non_empty(references),
            published_date=published_date,
            raw={source: raw},
        )


@dataclass
class TargetVulnerability:
    target_id: str
    vulnerability_id: str
    target_name: str | None = None
    affected_versions: list[str] = field(default_factory=list)
    fixed_versions: list[str] = field(default_factory=list)
    matched_queries: list[str] = field(default_factory=list)
    evidence_sources: list[dict[str, Any]] = field(default_factory=list)
    id: str | None = None
    first_seen_at: datetime = field(default_factory=utc_now)
    last_seen_at: datetime = field(default_factory=utc_now)

    def add_evidence(self, *, source: str, matched_query: str, evidence: dict[str, Any]) -> None:
        self.matched_queries = _unique_non_empty([*self.matched_queries, matched_query])
        if not any(item.get("source") == source for item in self.evidence_sources):
            self.evidence_sources.append({"source": source, "evidence": evidence})
        self.last_seen_at = utc_now()
