from datetime import date

from updater.presentation.discord_bot.formatting import (
    SEVERITY_COLORS,
    build_finding_embed,
    build_summary_message,
    group_findings,
)


def _finding(
    advisory_id="CVE-2024-12647",
    aliases=None,
    cvss_score=7.8,
    severity="HIGH",
    description="desc",
    references=None,
    target_names=("Canon MF654Cdw",),
):
    return {
        "advisory_id": advisory_id,
        "aliases": list(aliases or []),
        "cvss_score": cvss_score,
        "severity": severity,
        "description": description,
        "references": list(references or []),
        "target_names": list(target_names),
    }


def test_severity_colors_match_spec():
    assert SEVERITY_COLORS["CRITICAL"] == 0xCC0000
    assert SEVERITY_COLORS["HIGH"] == 0xFF7700
    assert SEVERITY_COLORS["MEDIUM"] == 0xFFCC00
    assert SEVERITY_COLORS["LOW"] == 0x28A745
    assert SEVERITY_COLORS["INFORMATIONAL"] == 0x999999
    assert SEVERITY_COLORS["NONE"] == 0x999999


def test_embed_uses_cve_id_when_available():
    embed = build_finding_embed(_finding(advisory_id="CVE-2024-12647"))
    assert embed.title == "CVE-2024-12647"


def test_embed_uses_zdi_id_when_no_cve():
    finding = _finding(advisory_id="ZDI-26-280", aliases=[])
    embed = build_finding_embed(finding)
    assert embed.title == "ZDI-26-280"


def test_embed_prefers_cve_alias_over_zdi_advisory_id():
    finding = _finding(advisory_id="ZDI-26-280", aliases=["CVE-2024-99999"])
    embed = build_finding_embed(finding)
    assert embed.title == "CVE-2024-99999"


def test_embed_joins_multiple_target_names():
    finding = _finding(target_names=("Canon MF654Cdw", "Canon MF656Cdw"))
    embed = build_finding_embed(finding)
    target_field = next(f for f in embed.fields if f.name == "Target")
    assert target_field.value == "Canon MF654Cdw, Canon MF656Cdw"


def test_embed_color_matches_severity():
    embed = build_finding_embed(_finding(severity="HIGH"))
    assert embed.color.value == 0xFF7700


def test_embed_color_falls_back_to_grey_for_unknown_severity():
    embed = build_finding_embed(_finding(severity=None))
    assert embed.color.value == 0x999999


def test_embed_includes_cvss_and_description():
    embed = build_finding_embed(_finding(cvss_score=7.8, description="some text"))
    fields = {f.name: f.value for f in embed.fields}
    assert fields["CVSS"] == "7.8"
    assert "some text" in embed.description


def test_embed_lists_references_as_bullets():
    finding = _finding(references=["https://a", "https://b"])
    embed = build_finding_embed(finding)
    fields = {f.name: f.value for f in embed.fields}
    assert "- https://a" in fields["References"]
    assert "- https://b" in fields["References"]


def test_summary_message_format():
    msg = build_summary_message(
        report_date=date(2026, 5, 20),
        targets_processed=5,
        new_findings=3,
        errors=0,
    )
    assert msg == (
        "Daily Vulnerability Report — 2026-05-20\n"
        "Targets processed: 5\n"
        "New findings: 3\n"
        "Errors: 0"
    )


def test_group_findings_merges_same_vulnerability():
    snapshot = {
        "target_vulnerabilities": [
            {
                "advisory_id": "CVE-2024-12647",
                "aliases": [],
                "cvss_score": 7.8,
                "severity": "HIGH",
                "description": "desc",
                "references": ["https://x"],
                "affected_targets": [
                    {"target_name": "Canon MF654Cdw"},
                    {"target_name": "Canon MF656Cdw"},
                ],
            }
        ]
    }
    findings = group_findings(snapshot)
    assert len(findings) == 1
    assert findings[0]["target_names"] == ["Canon MF654Cdw", "Canon MF656Cdw"]
    assert findings[0]["advisory_id"] == "CVE-2024-12647"
