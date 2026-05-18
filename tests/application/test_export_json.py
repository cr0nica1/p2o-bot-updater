from datetime import datetime, timezone

from updater.application.export_json import ExportService
from updater.domain.models import Target, TargetVulnerability, Vulnerability


class FakeTargetRepository:
    def list_all(self):
        return [Target(id="target-1", name="Adobe Reader", aliases=["Acrobat"])]


class FakeVulnerabilityRepository:
    def list_all(self):
        return [
            Vulnerability(
                id="vuln-1",
                advisory_id="CVE-2025-1234",
                sources=["nvd"],
                published_date=datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            )
        ]


class FakeTargetVulnerabilityRepository:
    def list_all(self):
        return [TargetVulnerability(target_id="target-1", vulnerability_id="vuln-1", matched_queries=["Adobe Reader"])]


def test_export_service_returns_json_compatible_snapshot():
    service = ExportService(FakeTargetRepository(), FakeVulnerabilityRepository(), FakeTargetVulnerabilityRepository())

    snapshot = service.snapshot()

    assert snapshot["targets"][0]["name"] == "Adobe Reader"
    assert snapshot["vulnerabilities"][0]["advisory_id"] == "CVE-2025-1234"
    assert snapshot["vulnerabilities"][0]["published_date"] == "2025-01-02T03:04:05+00:00"
    assert snapshot["target_vulnerabilities"][0]["target_id"] == "target-1"
