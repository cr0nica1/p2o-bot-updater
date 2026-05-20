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
    description = finding.get("description") or ""
    severity = finding.get("severity") or "None"

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color(_color_for(finding.get("severity"))),
    )

    target_names = finding.get("target_names") or []
    embed.add_field(name="Target", value=", ".join(target_names) or "—", inline=False)
    embed.add_field(name="Severity", value=severity, inline=True)

    cvss = finding.get("cvss_score")
    embed.add_field(name="CVSS", value="—" if cvss is None else f"{cvss}", inline=True)

    references = finding.get("references") or []
    if references:
        embed.add_field(
            name="References",
            value="\n".join(f"- {ref}" for ref in references),
            inline=False,
        )

    return embed


def build_summary_message(
    *,
    report_date: date,
    targets_processed: int,
    new_findings: int,
    errors: int,
) -> str:
    return (
        f"Daily Vulnerability Report — {report_date.isoformat()}\n"
        f"Targets processed: {targets_processed}\n"
        f"New findings: {new_findings}\n"
        f"Errors: {errors}"
    )


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
