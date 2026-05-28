from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import discord

from updater.application.export_json import ExportService
from updater.application.import_targets import ImportTargetsService
from updater.application.sync_vulnerabilities import SyncVulnerabilitiesService
from updater.domain.models import Target, TargetVulnerability, Vulnerability
from updater.domain.repositories import (
    TargetRepository,
    TargetVersionRepository,
    TargetVulnerabilityRepository,
    VulnerabilityRepository,
    VulnerabilitySource,
)
from updater.infrastructure.csv_loader import CsvTargetLoader
from updater.presentation.discord_bot.config import ConfigError, update_schedule
from updater.presentation.discord_bot.formatting import (
    build_finding_embed,
    group_findings,
)


@dataclass
class CommandResult:
    text: str = ""
    embeds: list[discord.Embed] = field(default_factory=list)
    ephemeral: bool = False


@dataclass
class Services:
    target_repo: TargetRepository
    version_repo: TargetVersionRepository
    vulnerability_repo: VulnerabilityRepository
    target_vulnerability_repo: TargetVulnerabilityRepository
    sources: list[VulnerabilitySource]


_CVE_YEAR_RE = re.compile(r"\bCVE-(\d{4})-\d{4,7}\b", re.IGNORECASE)
_ZDI_YEAR_RE = re.compile(r"\bZDI-(?:CAN-)?(\d{2,4})-\d{3,7}\b", re.IGNORECASE)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UTC_PLUS_7 = timezone(timedelta(hours=7))


def _sorted_targets(services: Services) -> list[Target]:
    return sorted(services.target_repo.list_all(), key=lambda target: target.name.casefold())


def _target_storage_id(target: Target) -> str:
    return target.id or target.normalized_name


def _vulnerability_lookup(vulnerabilities: list[Vulnerability]) -> dict[str, Vulnerability]:
    lookup: dict[str, Vulnerability] = {}
    for vulnerability in vulnerabilities:
        if vulnerability.id:
            lookup[vulnerability.id] = vulnerability
        lookup[vulnerability.advisory_id] = vulnerability
    return lookup


def filter_findings_to_created_since(
    findings: list[dict[str, Any]],
    vulnerabilities: list[Vulnerability],
    sync_started_at: datetime,
) -> list[dict[str, Any]]:
    vulnerabilities_by_id = _vulnerability_lookup(vulnerabilities)
    return [
        finding
        for finding in findings
        if (vulnerability := vulnerabilities_by_id.get(finding.get("advisory_id", ""))) is not None
        and vulnerability.created_at >= sync_started_at
    ]


def _vulnerability_sort_time(vulnerability: Vulnerability) -> datetime:
    return vulnerability.published_date or vulnerability.created_at


def _finding_for_target(vulnerability: Vulnerability, target: Target) -> dict[str, Any]:
    return {
        "advisory_id": vulnerability.advisory_id,
        "aliases": list(vulnerability.aliases),
        "cvss_score": vulnerability.cvss_score,
        "severity": vulnerability.severity,
        "description": vulnerability.description or "",
        "references": list(vulnerability.references),
        "target_names": [target.name],
    }


def _parse_date_filter(value: str | None) -> date | None:
    if value is None:
        return None
    if not _DATE_RE.match(value):
        raise ValueError("dates must use YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("dates must use YYYY-MM-DD format") from exc


def _validate_search_year(year: int | None, today: date) -> None:
    if year is None:
        return
    if year < 1999 or year > today.year + 1:
        raise ValueError(f"year must be between 1999 and {today.year + 1}")


_VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL", "NONE"}


def _validate_severity(severity: str | None) -> str | None:
    if severity is None:
        return None
    upper = severity.strip().upper()
    if upper not in _VALID_SEVERITIES:
        raise ValueError(f"severity must be one of: {', '.join(sorted(_VALID_SEVERITIES))}")
    return upper


def _finding_years(finding: dict[str, Any], vulnerability: Vulnerability | None) -> set[int]:
    values = [finding.get("advisory_id", ""), *finding.get("aliases", [])]
    years = {int(match.group(1)) for value in values for match in _CVE_YEAR_RE.finditer(value)}
    for value in values:
        for match in _ZDI_YEAR_RE.finditer(value):
            raw_year = int(match.group(1))
            years.add(2000 + raw_year if raw_year < 100 else raw_year)
    if vulnerability is not None and vulnerability.published_date is not None:
        years.add(vulnerability.published_date.year)
    return years


def _created_date(vulnerability: Vulnerability | None, tz=UTC_PLUS_7) -> date | None:
    if vulnerability is None:
        return None
    created_at = vulnerability.created_at
    if created_at.tzinfo is None:
        return created_at.date()
    return created_at.astimezone(tz).date()


def _format_search_summary(
    *,
    total: int,
    severity: str | None,
    year: int | None,
    from_day: date | None,
    to_day: date | None,
    scope_all: bool,
) -> str:
    filters: list[str] = []
    if severity is not None:
        filters.append(f"severity: {severity}")
    if year is not None:
        filters.append(f"year: {year}")
    if scope_all:
        filters.append("scope: all")
    elif from_day is not None and to_day is not None:
        filters.append(f"collected: {from_day.isoformat()} to {to_day.isoformat()}")
    return f"Found {total} vulnerabilities (" + ", ".join(filters) + ")"


async def handle_list_targets(services: Services) -> CommandResult:
    targets = _sorted_targets(services)
    if not targets:
        return CommandResult(text="No targets configured.")
    lines = [f"{index}. {target.name}" for index, target in enumerate(targets, start=1)]
    return CommandResult(text="Targets:\n" + "\n".join(lines))


async def handle_show_target(services: Services, *, target_id: int, limit: int | None) -> CommandResult:
    targets = _sorted_targets(services)
    if target_id < 1 or target_id > len(targets):
        return CommandResult(
            text=f"Invalid target ID. Use /list-targets to see available targets (1-{len(targets)}).",
            ephemeral=True,
        )

    target = targets[target_id - 1]
    storage_id = _target_storage_id(target)
    links = [
        link
        for link in services.target_vulnerability_repo.list_all()
        if link.target_id == storage_id
    ]
    vulnerabilities_by_id = _vulnerability_lookup(services.vulnerability_repo.list_all())
    vulnerabilities = [
        vulnerabilities_by_id[link.vulnerability_id]
        for link in links
        if link.vulnerability_id in vulnerabilities_by_id
    ]
    vulnerabilities.sort(key=_vulnerability_sort_time, reverse=True)

    total = len(vulnerabilities)
    if limit is not None and limit > 0:
        vulnerabilities = vulnerabilities[:limit]

    lines = [
        f"Target #{target_id}: {target.name}",
        f"Aliases: {', '.join(target.aliases) or '—'}",
        f"Vendor: {target.vendor or '—'}",
        f"Category: {target.category or '—'}",
    ]
    if total == 0:
        lines.append("No vulnerabilities found.")
    else:
        lines.append(f"Showing {len(vulnerabilities)} of {total} vulnerabilities")

    embeds = [build_finding_embed(_finding_for_target(vulnerability, target)) for vulnerability in vulnerabilities]
    return CommandResult(text="\n".join(lines), embeds=embeds)


async def handle_add_target(
    services: Services,
    *,
    name: str,
    aliases: list[str] | None = None,
    vendor: str | None = None,
    category: str | None = None,
) -> CommandResult:
    target = Target(
        name=name,
        aliases=list(aliases or []),
        vendor=vendor,
        category=category,
    )
    services.target_repo.upsert(target)
    return CommandResult(text=f"Added target: {name}")


async def handle_remove_target(services: Services, *, names: list[str]) -> CommandResult:
    removed: list[str] = []
    missing: list[str] = []
    resolved: list[tuple[str, str]] = []

    for name in names:
        target = services.target_repo.find_by_name(name)
        if target is None:
            missing.append(name)
            continue
        target_id = target.id or target.normalized_name
        resolved.append((name, target_id))

    target_ids = {tid for _, tid in resolved}
    all_links = services.target_vulnerability_repo.list_all()

    candidate_ids = {
        link.vulnerability_id
        for link in all_links
        if link.target_id in target_ids
    }
    owned_ids = {
        vid
        for vid in candidate_ids
        if all(
            link.target_id in target_ids
            for link in all_links
            if link.vulnerability_id == vid
        )
    }

    for vid in owned_ids:
        services.vulnerability_repo.delete(vid)

    for name, tid in resolved:
        services.target_vulnerability_repo.delete_by_target(tid)
        services.target_repo.delete(name)
        removed.append(name)

    parts: list[str] = []
    if removed:
        parts.append("Removed: " + ", ".join(removed))
    if missing:
        parts.append("Not found: " + ", ".join(missing))
    return CommandResult(text="\n".join(parts) or "Nothing to do.")


async def handle_clear_database(services: Services, *, confirm: str) -> CommandResult:
    if confirm != "DELETE":
        return CommandResult(text="Refusing to clear database: type DELETE to confirm.", ephemeral=True)

    counts = {
        "targets": services.target_repo.delete_all(),
        "versions": services.version_repo.delete_all(),
        "vulnerabilities": services.vulnerability_repo.delete_all(),
        "links": services.target_vulnerability_repo.delete_all(),
    }
    return CommandResult(
        text=(
            "Database cleared.\n"
            f"targets={counts['targets']} versions={counts['versions']} "
            f"vulnerabilities={counts['vulnerabilities']} links={counts['links']}"
        ),
        ephemeral=True,
    )


async def handle_import_targets(services: Services, *, csv_bytes: bytes) -> CommandResult:
    import tempfile

    with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as tmp:
        tmp.write(csv_bytes)
        tmp_path = Path(tmp.name)

    try:
        load_result = CsvTargetLoader().load(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    import_result = ImportTargetsService(
        services.target_repo, services.version_repo
    ).import_items([(item.target, item.version) for item in load_result.items])

    lines = [
        "Import complete.",
        f"Targets imported: {import_result.targets_imported}",
        f"Versions imported: {import_result.versions_imported}",
        f"Errors: {len(load_result.errors)}",
    ]
    lines.extend(load_result.errors[:10])
    return CommandResult(text="\n".join(lines))


async def handle_add_vuln(
    services: Services,
    *,
    advisory_id: str,
    description: str | None,
    cvss_score: float | None,
    severity: str | None,
    references: list[str],
    target_name: str | None,
) -> CommandResult:
    target = None
    if target_name:
        target = services.target_repo.find_by_name(target_name)
        if target is None:
            return CommandResult(text=f"Target {target_name!r} not found.")

    vuln = Vulnerability(
        advisory_id=advisory_id,
        description=description or None,
        cvss_score=cvss_score,
        severity=severity,
        references=list(references),
        sources=["manual"],
    )
    saved = services.vulnerability_repo.upsert(vuln)

    if target is not None:
        link = TargetVulnerability(
            target_id=target.id or target.normalized_name,
            target_name=target.name,
            vulnerability_id=saved.id or saved.advisory_id,
        )
        link.add_evidence(source="manual", matched_query=target.name, evidence={"source": "manual"})
        services.target_vulnerability_repo.upsert(link)

    return CommandResult(text=f"Added vulnerability: {advisory_id}")


async def handle_sync_cves(services: Services, *, target_name: str | None) -> CommandResult:
    if target_name is not None and services.target_repo.find_by_name(target_name) is None:
        return CommandResult(text=f"Target {target_name!r} not found.")
    sync_started_at = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    sync = SyncVulnerabilitiesService(
        services.target_repo,
        services.vulnerability_repo,
        services.target_vulnerability_repo,
        services.sources,
    )
    result = await asyncio.to_thread(sync.sync_one, target_name) if target_name else await asyncio.to_thread(sync.sync_all)

    vulnerabilities = await asyncio.to_thread(services.vulnerability_repo.list_all)
    snapshot = await asyncio.to_thread(
        ExportService(
            services.target_repo,
            services.vulnerability_repo,
            services.target_vulnerability_repo,
        ).snapshot
    )
    findings = group_findings(snapshot)

    if target_name:
        findings = [
            f for f in findings if target_name.strip().lower() in [t.lower() for t in f["target_names"]]
        ]
    findings = filter_findings_to_created_since(findings, vulnerabilities, sync_started_at)

    summary = (
        f"Sync complete. targets_processed={result.targets_processed} "
        f"vulnerabilities_seen={result.vulnerabilities_seen} "
        f"links_updated={result.links_updated} errors={len(result.errors)}"
    )
    embeds = [build_finding_embed(f) for f in findings]
    return CommandResult(text=summary, embeds=embeds)


async def handle_search_vulns(
    services: Services,
    *,
    severity: str | None,
    year: int | None,
    from_date: str | None,
    to_date: str | None,
    today: date | None = None,
) -> CommandResult:
    today = today or datetime.now(UTC_PLUS_7).date()
    try:
        normalized_severity = _validate_severity(severity)
        _validate_search_year(year, today)
        from_day = _parse_date_filter(from_date)
        to_day = _parse_date_filter(to_date)
    except ValueError as exc:
        return CommandResult(text=str(exc), ephemeral=True)

    has_explicit_date_filter = from_day is not None or to_day is not None
    scope_all = normalized_severity is not None and year is None and not has_explicit_date_filter

    if has_explicit_date_filter:
        if from_day is None:
            from_day = to_day
        elif to_day is None:
            to_day = from_day
    elif normalized_severity is None:
        from_day = today
        to_day = today

    if from_day is not None and to_day is not None and from_day > to_day:
        return CommandResult(text="from_date must be before or equal to to_date", ephemeral=True)

    vulnerabilities = await asyncio.to_thread(services.vulnerability_repo.list_all)
    vulnerabilities_by_id: dict[str, Vulnerability] = {}
    for vulnerability in vulnerabilities:
        if vulnerability.id:
            vulnerabilities_by_id[vulnerability.id] = vulnerability
        vulnerabilities_by_id[vulnerability.advisory_id] = vulnerability

    snapshot = await asyncio.to_thread(
        ExportService(
            services.target_repo,
            services.vulnerability_repo,
            services.target_vulnerability_repo,
        ).snapshot
    )
    findings = group_findings(snapshot)

    filtered: list[dict[str, Any]] = []
    for finding in findings:
        vulnerability = vulnerabilities_by_id.get(finding.get("advisory_id", ""))
        if from_day is not None:
            created_day = _created_date(vulnerability)
            if created_day is None or created_day < from_day or created_day > to_day:
                continue
        if year is not None and year not in _finding_years(finding, vulnerability):
            continue
        if normalized_severity is not None:
            vuln_severity = (finding.get("severity") or "NONE").upper()
            if vuln_severity != normalized_severity:
                continue
        filtered.append(finding)

    if not filtered:
        return CommandResult(text="No vulnerabilities found matching the filters.")

    summary = _format_search_summary(
        total=len(filtered), severity=normalized_severity, year=year,
        from_day=from_day, to_day=to_day, scope_all=scope_all,
    )
    return CommandResult(
        text=summary,
        embeds=[build_finding_embed(finding) for finding in filtered],
    )


async def handle_set_schedule(
    *,
    env_path: Path,
    sync_time: str,
    notify_time: str,
) -> CommandResult:
    try:
        update_schedule(env_path, sync_time=sync_time, notify_time=notify_time)
    except ConfigError as exc:
        return CommandResult(text=f"Invalid schedule: {exc}")
    return CommandResult(text=f"Schedule updated. SYNC_TIME={sync_time}, NOTIFY_TIME={notify_time}")


async def handle_show_schedule(
    *, sync_time: tuple[int, int], notify_time: tuple[int, int]
) -> CommandResult:
    return CommandResult(
        text=(
            f"SYNC_TIME={sync_time[0]:02d}:{sync_time[1]:02d}\n"
            f"NOTIFY_TIME={notify_time[0]:02d}:{notify_time[1]:02d}"
        )
    )
