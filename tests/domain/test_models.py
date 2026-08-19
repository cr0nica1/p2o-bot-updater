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


def test_search_queries_use_search_names_when_set():
    target = Target(name="Chroma", aliases=["unused"], search_names=["ChromaDB"])
    assert target.search_queries() == ["ChromaDB"]


def test_search_queries_fall_back_to_name_and_aliases():
    target = Target(name="LiteLLM", aliases=["Lite LLM"])
    assert target.search_queries() == ["LiteLLM", "Lite LLM"]


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


def test_target_vulnerability_stores_target_name():
    link = TargetVulnerability(target_id="target-1", vulnerability_id="vuln-1", target_name="Adobe Reader")

    assert link.target_name == "Adobe Reader"


def test_target_vulnerability_merges_evidence_without_duplicates():
    link = TargetVulnerability(target_id="target-1", vulnerability_id="vuln-1")

    link.add_evidence(source="nvd", matched_query="Adobe Reader", evidence={"id": "CVE-2025-1234"})
    link.add_evidence(source="nvd", matched_query="Adobe Reader", evidence={"id": "CVE-2025-1234"})
    link.add_evidence(source="zdi", matched_query="Acrobat Reader", evidence={"id": "ZDI-CAN-12345"})

    assert link.matched_queries == ["Adobe Reader", "Acrobat Reader"]
    assert [item["source"] for item in link.evidence_sources] == ["nvd", "zdi"]


from updater.domain.models import Target, VendorConfig


def test_target_stores_vendor_alias():
    target = Target(name="Canon MF654Cdw", vendor="Canon", vendor_alias="mf654cdw")

    assert target.vendor_alias == "mf654cdw"


def test_vendor_config_stores_crawler_settings():
    config = VendorConfig(
        vendor="Canon",
        url_template="https://vendor.example/downloads/{alias}/firmware",
        attr_id="firmware",
        regex=r"Version ([^<]+).*href=\"([^\"]+)\"",
    )

    assert config.vendor == "Canon"
    assert config.normalized_vendor == "canon"
    assert config.url_template == "https://vendor.example/downloads/{alias}/firmware"
    assert config.attr_id == "firmware"
    assert config.regex == r"Version ([^<]+).*href=\"([^\"]+)\""


def test_vendor_config_new_fields_default_to_legacy_behavior():
    from updater.domain.models import VendorConfig

    config = VendorConfig(vendor="Canon", url_template="https://x/{alias}", regex="(.+)")
    assert config.attr_id == ""
    assert config.target is None
    assert config.fetch == "browser"
    assert config.selector is None
    assert config.select == "first"
    assert config.normalized_target is None


def test_vendor_config_normalized_target():
    from updater.domain.models import VendorConfig

    config = VendorConfig(vendor="Chroma", url_template="https://x", regex="(.+)", target="  Chroma  ")
    assert config.normalized_target == "chroma"


def test_target_version_previous_version_defaults_to_none():
    from updater.domain.models import TargetVersion
    assert TargetVersion().previous_version is None
    assert TargetVersion(previous_version="1.0.0").previous_version == "1.0.0"
