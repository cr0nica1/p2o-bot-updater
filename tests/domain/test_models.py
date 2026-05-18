from datetime import datetime, timezone

from updater.domain.models import (
    Target,
    TargetVersion,
    TargetVulnerability,
    Vulnerability,
    normalize_name,
)


def test_normalize_name_trims_and_lowercases_spaces():
    assert normalize_name("  Adobe   Acrobat Reader  ") == "adobe acrobat reader"


def test_target_search_queries_include_name_and_unique_aliases():
    target = Target(name="Adobe Acrobat Reader", aliases=["Adobe Reader", "Adobe Reader", ""])

    assert target.search_queries() == ["Adobe Acrobat Reader", "Adobe Reader"]


def test_zdi_vulnerability_prefers_cve_and_keeps_zdi_alias():
    vuln = Vulnerability.from_source(
        source="zdi",
        advisory_id="ZDI-CAN-12345",
        cve_id="CVE-2025-1234",
        cvss_score=9.8,
        severity="critical",
        description="Example vulnerability",
        references=["https://example.test/zdi"],
        published_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
        raw={"zdi_id": "ZDI-CAN-12345"},
    )

    assert vuln.advisory_id == "CVE-2025-1234"
    assert vuln.aliases == ["ZDI-CAN-12345"]
    assert vuln.sources == ["zdi"]


def test_target_version_allows_missing_version():
    version = TargetVersion(target_id="target-1")

    assert version.version is None
    assert version.version_type is None


def test_target_vulnerability_merges_evidence_without_duplicates():
    link = TargetVulnerability(target_id="target-1", vulnerability_id="vuln-1")

    link.add_evidence(source="nvd", matched_query="Adobe Reader", evidence={"id": "CVE-2025-1234"})
    link.add_evidence(source="nvd", matched_query="Adobe Reader", evidence={"id": "CVE-2025-1234"})
    link.add_evidence(source="zdi", matched_query="Acrobat Reader", evidence={"id": "ZDI-CAN-12345"})

    assert link.matched_queries == ["Adobe Reader", "Acrobat Reader"]
    assert [item["source"] for item in link.evidence_sources] == ["nvd", "zdi"]
