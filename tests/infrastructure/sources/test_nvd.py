from updater.domain.models import Target
from updater.infrastructure.sources.nvd import NvdSource, normalize_nvd_item


def test_normalize_nvd_item_extracts_required_fields():
    raw = {
        "cve": {
            "id": "CVE-2025-1234",
            "published": "2025-01-02T03:04:05.000",
            "descriptions": [{"lang": "en", "value": "Example vulnerability"}],
            "references": {"referenceData": [{"url": "https://example.test/ref"}]},
            "metrics": {
                "cvssMetricV31": [{"cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL"}}]
            },
        }
    }

    vulnerability = normalize_nvd_item(raw)

    assert vulnerability.advisory_id == "CVE-2025-1234"
    assert vulnerability.cvss_score == 9.8
    assert vulnerability.severity == "critical"
    assert vulnerability.description == "Example vulnerability"
    assert vulnerability.references == ["https://example.test/ref"]
    assert vulnerability.sources == ["nvd"]


def test_normalize_nvd_item_extracts_cvss_v2_severity():
    raw = {
        "cve": {
            "id": "CVE-2025-5678",
            "published": "2025-03-01T00:00:00.000",
            "descriptions": [{"lang": "en", "value": "V2 test"}],
            "references": {"referenceData": []},
            "metrics": {
                "cvssMetricV2": [{"cvssData": {"baseScore": 7.5}, "baseSeverity": "HIGH"}]
            },
        }
    }
    vulnerability = normalize_nvd_item(raw)
    assert vulnerability.cvss_score == 7.5
    assert vulnerability.severity == "high"


def test_nvd_source_builds_query_request(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"vulnerabilities": []}

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return FakeResponse()

    source = NvdSource(get=fake_get)

    result = source.search(Target(name="Adobe Acrobat Reader"), "Adobe Reader")

    assert result == []
    assert calls[0][0] == "https://services.nvd.nist.gov/rest/json/cves/2.0"
    assert calls[0][1]["keywordSearch"] == "Adobe Reader"
    assert calls[0][2] == 30
