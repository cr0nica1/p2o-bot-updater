from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import discord

from updater.application.export_json import ExportService
from updater.application.import_targets import ImportTargetsService
from updater.application.sync_vulnerabilities import SyncVulnerabilitiesService
from updater.domain.models import Target, TargetVersion, TargetVulnerability, Vulnerability
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


@dataclass
class Services:
    target_repo: TargetRepository
    version_repo: TargetVersionRepository
    vulnerability_repo: VulnerabilityRepository
    target_vulnerability_repo: TargetVulnerabilityRepository
    sources: list[VulnerabilitySource]


async def handle_list_targets(services: Services) -> CommandResult:
    targets = services.target_repo.list_all()
    if not targets:
        return CommandResult(text="No targets configured.")
    lines = [f"- {t.name}" for t in targets]
    return CommandResult(text="Targets:\n" + "\n".join(lines))


async def handle_show_target(services: Services, *, name: str) -> CommandResult:
    target = services.target_repo.find_by_name(name)
    if target is None:
        return CommandResult(text=f"Target {name!r} not found.")
    target_id = target.id or target.normalized_name
    linked = sum(
        1
        for link in services.target_vulnerability_repo.list_all()
        if link.target_id == target_id
    )
    lines = [
        f"Name: {target.name}",
        f"Aliases: {', '.join(target.aliases) or '—'}",
        f"Vendor: {target.vendor or '—'}",
        f"Category: {target.category or '—'}",
        f"Vulnerabilities: {linked}",
    ]
    return CommandResult(text="\n".join(lines))


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
    for name in names:
        target = services.target_repo.find_by_name(name)
        if target is None:
            missing.append(name)
            continue
        target_id = target.id or target.normalized_name
        services.target_vulnerability_repo.delete_by_target(target_id)
        services.target_repo.delete(name)
        removed.append(name)

    parts: list[str] = []
    if removed:
        parts.append("Removed: " + ", ".join(removed))
    if missing:
        parts.append("Not found: " + ", ".join(missing))
    return CommandResult(text="\n".join(parts) or "Nothing to do.")


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
    description: str,
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
    sync = SyncVulnerabilitiesService(
        services.target_repo,
        services.vulnerability_repo,
        services.target_vulnerability_repo,
        services.sources,
    )
    result = sync.sync_one(target_name) if target_name else sync.sync_all()

    snapshot = ExportService(
        services.target_repo,
        services.vulnerability_repo,
        services.target_vulnerability_repo,
    ).snapshot()
    findings = group_findings(snapshot)

    if target_name:
        findings = [
            f for f in findings if target_name.strip().lower() in [t.lower() for t in f["target_names"]]
        ]

    summary = (
        f"Sync complete. targets_processed={result.targets_processed} "
        f"vulnerabilities_seen={result.vulnerabilities_seen} "
        f"links_updated={result.links_updated} errors={len(result.errors)}"
    )
    embeds = [build_finding_embed(f) for f in findings]
    return CommandResult(text=summary, embeds=embeds)


async def handle_set_schedule(
    services: Services,
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
