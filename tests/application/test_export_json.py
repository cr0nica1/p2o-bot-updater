from datetime import datetime, timezone

from updater.application.export_json import ExportService
from updater.domain.models import Target, TargetVulnerability, Vulnerability


class FakeTargetRepository:
    def list_all(self):
        return [Target(id="target-1", name="Adobe Reader", aliases=["Acrobat"])]


class FakeVulnerabilityRepository:
    def __init__(self, items=None):
        self._items = items or [
            Vulnerability(
                id="vuln-1",
                advisory_id="CVE-2025-1234",
                sources=["nvd"],
                cvss_score=7.5,
                severity="HIGH",
                description="Buffer overflow in Adobe Reader",
                published_date=datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
                references=["https://example.com/advisory"],
            )
        ]

    def list_all(self):
        return list(self._items)


class FakeTargetVulnerabilityRepository:
    def list_all(self):
        link = TargetVulnerability(
            target_id="target-1",
            target_name="Adobe Reader",
            vulnerability_id="vuln-1",
            matched_queries=["Adobe Reader"],
            first_seen_at=datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            last_seen_at=datetime(2025, 6, 2, 12, 0, 0, tzinfo=timezone.utc),
        )
        link.evidence_sources = [
            {
                "source": "nvd",
                "evidence": {
                    "query": "Adobe Reader",
                    "nvd": {"cve": {"id": "CVE-2025-1234"}},
                },
            }
        ]
        return [link]


def test_snapshot_returns_vulnerabilities_with_grouped_affected_targets():
    service = ExportService(
        FakeTargetRepository(),
        FakeVulnerabilityRepository(),
        FakeTargetVulnerabilityRepository(),
    )

    snapshot = service.snapshot()

    assert list(snapshot.keys()) == ["target_vulnerabilities"]
    entries = snapshot["target_vulnerabilities"]
    assert len(entries) == 1
    entry = entries[0]

    assert entry["advisory_id"] == "CVE-2025-1234"
    assert entry["cvss_score"] == 7.5
    assert entry["severity"] == "HIGH"
    assert entry["description"] == "Buffer overflow in Adobe Reader"
    assert entry["published_date"] == "2025-01-02T03:04:05+00:00"
    assert entry["references"] == ["https://example.com/advisory"]

    target = entry["affected_targets"][0]
    assert target["target_name"] == "Adobe Reader"
    assert target["first_seen_at"] == "2025-06-01T12:00:00+00:00"
    assert target["last_seen_at"] == "2025-06-02T12:00:00+00:00"


def test_snapshot_strips_query_fields():
    service = ExportService(
        FakeTargetRepository(),
        FakeVulnerabilityRepository(),
        FakeTargetVulnerabilityRepository(),
    )

    snapshot = service.snapshot()

    entry = snapshot["target_vulnerabilities"][0]
    assert "matched_queries" not in entry["affected_targets"][0]
    for evidence_source in entry["affected_targets"][0].get("evidence_sources", []):
        assert "query" not in evidence_source.get("evidence", {})


def test_snapshot_groups_duplicate_advisory_ids_under_affected_targets():
    vulnerability = Vulnerability(
        id="vuln-1",
        advisory_id="CVE-2024-12647",
        sources=["nvd", "zdi"],
        cvss_score=7.8,
        severity="HIGH",
        description="Canon printer vulnerability",
        references=["https://example.com/cve-2024-12647"],
    )

    class DuplicateTargetVulnerabilityRepository:
        def list_all(self):
            first = TargetVulnerability(
                target_id="target-1",
                target_name="Canon imageCLASS MF654Cdw",
                vulnerability_id="vuln-1",
                matched_queries=["Canon imageCLASS MF654Cdw"],
            )
            first.evidence_sources = [
                {
                    "source": "nvd",
                    "evidence": {
                        "query": "Canon imageCLASS MF654Cdw",
                        "nvd": {"cve": {"id": "CVE-2024-12647"}},
                    },
                }
            ]
            second = TargetVulnerability(
                target_id="target-2",
                target_name="Canon imageCLASS MF656Cdw",
                vulnerability_id="vuln-1",
                matched_queries=["Canon imageCLASS MF656Cdw"],
            )
            second.evidence_sources = [
                {
                    "source": "zdi",
                    "evidence": {
                        "query": "Canon imageCLASS MF656Cdw",
                        "zdi": {"zdi_id": "ZDI-24-001"},
                    },
                }
            ]
            return [first, second]

    service = ExportService(
        FakeTargetRepository(),
        FakeVulnerabilityRepository([vulnerability]),
        DuplicateTargetVulnerabilityRepository(),
    )

    snapshot = service.snapshot()

    entries = snapshot["target_vulnerabilities"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["advisory_id"] == "CVE-2024-12647"
    assert entry["sources"] == ["nvd", "zdi"]
    assert [target["target_name"] for target in entry["affected_targets"]] == [
        "Canon imageCLASS MF654Cdw",
        "Canon imageCLASS MF656Cdw",
    ]
    assert [
        target["evidence_sources"][0]["source"]
        for target in entry["affected_targets"]
    ] == ["nvd", "zdi"]


def test_snapshot_merges_same_target_across_queries_under_one_entry():
    vulnerability = Vulnerability(
        id="vuln-1",
        advisory_id="CVE-2025-9999",
        sources=["nvd"],
        cvss_score=9.0,
        description="Critical bug",
    )

    class MultiQueryTargetVulnerabilityRepository:
        def list_all(self):
            first_hit = TargetVulnerability(
                target_id="target-1",
                target_name="Adobe Reader",
                vulnerability_id="vuln-1",
                matched_queries=["Adobe Reader"],
                first_seen_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
                last_seen_at=datetime(2025, 6, 2, tzinfo=timezone.utc),
            )
            first_hit.evidence_sources = [
                {
                    "source": "nvd",
                    "evidence": {
                        "query": "Adobe Reader",
                        "nvd": {"cve": {"id": "CVE-2025-9999"}},
                    },
                }
            ]
            second_hit = TargetVulnerability(
                target_id="target-1",
                target_name="Adobe Reader",
                vulnerability_id="vuln-1",
                matched_queries=["Acrobat"],
                first_seen_at=datetime(2025, 6, 3, tzinfo=timezone.utc),
                last_seen_at=datetime(2025, 6, 4, tzinfo=timezone.utc),
            )
            second_hit.evidence_sources = [
                {
                    "source": "nvd",
                    "evidence": {
                        "query": "Acrobat",
                        "nvd": {"cve": {"id": "CVE-2025-9999"}},
                    },
                }
            ]
            return [first_hit, second_hit]

    service = ExportService(
        FakeTargetRepository(),
        FakeVulnerabilityRepository([vulnerability]),
        MultiQueryTargetVulnerabilityRepository(),
    )

    snapshot = service.snapshot()

    entries = snapshot["target_vulnerabilities"]
    assert len(entries) == 1
    affected = entries[0]["affected_targets"]
    assert len(affected) == 1
    assert affected[0]["target_name"] == "Adobe Reader"
    assert len(affected[0]["evidence_sources"]) == 2

