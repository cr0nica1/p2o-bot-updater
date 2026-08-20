from __future__ import annotations

from datetime import date
from typing import Any, Iterable

import discord


SEVERITY_COLORS: dict[str, int] = {
    "CRITICAL": 0xCC0000,
    "HIGH": 0xFF7700,
    "MEDIUM": 0xFFCC00,
    "LOW": 0x28A745,
    "INFORMATIONAL": 0x999999,
    "NONE": 0x999999,
}

_EMBED_TOTAL_LIMIT = 6000
_DESCRIPTION_LIMIT = 3500
_FIELD_VALUE_LIMIT = 1024
_TRUNCATION_SUFFIX = "…"


def _truncate(value: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    if limit <= len(_TRUNCATION_SUFFIX):
        return _TRUNCATION_SUFFIX[:limit]
    return value[: limit - len(_TRUNCATION_SUFFIX)] + _TRUNCATION_SUFFIX


def _embed_size(embed: discord.Embed) -> int:
    total = len(embed.title or "") + len(embed.description or "")
    total += sum(len(field.name) + len(field.value) for field in embed.fields)
    return total


def _pick_title(advisory_id: str, aliases: Iterable[str]) -> str:
    if advisory_id.upper().startswith("CVE-"):
        return advisory_id
    for alias in aliases:
        if alias.upper().startswith("CVE-"):
            return alias
    return advisory_id


def _color_for(severity: str | None) -> int:
    if not severity:
        return SEVERITY_COLORS["NONE"]
    return SEVERITY_COLORS.get(severity.upper(), SEVERITY_COLORS["NONE"])


def build_finding_embed(finding: dict[str, Any]) -> discord.Embed:
    advisory_id = finding["advisory_id"]
    aliases = finding.get("aliases") or []
    title = _pick_title(advisory_id, aliases)
    description = _truncate(finding.get("description") or "", _DESCRIPTION_LIMIT)
    severity = finding.get("severity") or "None"

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color(_color_for(finding.get("severity"))),
    )

    target_names = finding.get("target_names") or []
    embed.add_field(
        name="Target",
        value=_truncate(", ".join(target_names) or "—", _FIELD_VALUE_LIMIT),
        inline=False,
    )
    embed.add_field(name="Severity", value=severity, inline=True)

    cvss = finding.get("cvss_score")
    embed.add_field(name="CVSS", value="—" if cvss is None else f"{cvss}", inline=True)

    references = finding.get("references") or []
    if references:
        embed.add_field(
            name="References",
            value=_truncate("\n".join(f"- {ref}" for ref in references), _FIELD_VALUE_LIMIT),
            inline=False,
        )

    while _embed_size(embed) > _EMBED_TOTAL_LIMIT and embed.description:
        overflow = _embed_size(embed) - _EMBED_TOTAL_LIMIT
        embed.description = _truncate(embed.description, max(0, len(embed.description) - overflow))

    return embed


_DISCORD_CONTENT_LIMIT = 2000
_SEVERITY_ORDER = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
    "INFORMATIONAL": 4,
    "NONE": 5,
}


def _compact_finding_line(finding: dict[str, Any]) -> str:
    title = _pick_title(finding.get("advisory_id") or "", finding.get("aliases") or [])
    parts = [f"• {title}", (finding.get("severity") or "NONE").upper()]
    cvss = finding.get("cvss_score")
    if cvss is not None and cvss != "":
        parts.append(str(cvss))
    targets = ", ".join(finding.get("target_names") or [])
    if targets:
        parts.append(targets)
    return "  ".join(parts)


def _sort_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        findings,
        key=lambda finding: (
            _SEVERITY_ORDER.get((finding.get("severity") or "NONE").upper(), 9),
            _pick_title(finding.get("advisory_id") or "", finding.get("aliases") or []),
        ),
    )


def build_summary_message(
    *,
    report_date: date,
    stored_targets: int,
    stored_vulnerabilities: int,
    new_findings: list[dict[str, Any]] | None = None,
    errors: int = 0,
    version_changes=None,
) -> str:
    findings = _sort_findings(list(new_findings or []))
    header = [
        f"Daily update — {report_date.isoformat()}",
        f"New discoveries: {len(findings)}",
    ]
    extra: list[str] = []
    if version_changes:
        extra.append(f"Version updates: {len(version_changes)}")
        extra.extend(
            f"• {change.target_name}: {change.old_version} → {change.new_version}"
            for change in version_changes
        )
    if errors:
        extra.append(f"Errors: {errors}")
    extra.append(
        f"Already stored: {stored_targets} targets, {stored_vulnerabilities} vulnerabilities"
    )

    finding_lines = [_compact_finding_line(finding) for finding in findings]
    head = "\n".join(header)
    footer = "\n".join(extra)
    if not finding_lines:
        return "\n".join([head, *extra])

    included: list[str] = []
    omitted = 0
    for index, line in enumerate(finding_lines):
        remaining_after = len(finding_lines) - index - 1
        candidate = included + [line]
        rest = finding_lines[index + 1 :]
        all_body = "\n".join(candidate + rest)
        if _message_size(head, all_body, footer) <= _DISCORD_CONTENT_LIMIT:
            included.append(line)
            continue
        suffix = f"…and {remaining_after} more" if remaining_after else ""
        body_with_suffix = "\n".join(candidate + ([suffix] if suffix else []))
        if suffix and _message_size(head, body_with_suffix, footer) <= _DISCORD_CONTENT_LIMIT:
            included.append(line)
            omitted = remaining_after
            break
        omitted = remaining_after + 1
        break

    if omitted and included:
        included.append(f"…and {omitted} more")
    elif omitted and not included:
        included.append(f"…and {omitted} more")

    return "\n".join([head, *included, *extra])


def _message_size(head: str, body: str, footer: str) -> int:
    parts = [head]
    if body:
        parts.append(body)
    if footer:
        parts.append(footer)
    return len("\n".join(parts))


def build_version_update_message(*, report_date: date, changes) -> str:
    lines = [f"🔔 Version updates — {report_date.isoformat()}"]
    for change in changes:
        lines.append(f"• {change.target_name}: {change.old_version} → {change.new_version}")
    lines.append(f"{len(changes)} update(s)")
    return "\n".join(lines)


def group_findings(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten an ExportService snapshot into a list of finding dicts for embedding."""
    findings: list[dict[str, Any]] = []
    for entry in snapshot.get("target_vulnerabilities", []):
        target_names = [
            t.get("target_name") for t in entry.get("affected_targets", []) if t.get("target_name")
        ]
        findings.append(
            {
                "advisory_id": entry.get("advisory_id", ""),
                "aliases": list(entry.get("aliases") or []),
                "cvss_score": entry.get("cvss_score"),
                "severity": entry.get("severity"),
                "description": entry.get("description") or "",
                "references": list(entry.get("references") or []),
                "target_names": target_names,
            }
        )
    return findings
