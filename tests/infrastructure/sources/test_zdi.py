from updater.domain.models import Target
from updater.infrastructure.sources.zdi import ZdiSource, normalize_zdi_advisory, parse_zdi_search_results


def test_normalize_zdi_advisory_prefers_cve_id():
    raw = {
        "zdi_id": "ZDI-CAN-12345",
        "cve_id": "CVE-2025-1234",
        "cvss_score": 8.8,
        "severity": "High",
        "description": "Example ZDI advisory",
        "references": ["https://example.test/zdi"],
        "published_date": "2025-02-03",
    }

    vulnerability = normalize_zdi_advisory(raw)

    assert vulnerability.advisory_id == "CVE-2025-1234"
    assert vulnerability.aliases == ["ZDI-CAN-12345"]
    assert vulnerability.severity == "high"
    assert vulnerability.sources == ["zdi"]


def test_normalize_zdi_advisory_uses_zdi_id_without_cve():
    raw = {
        "zdi_id": "ZDI-CAN-99999",
        "cve_id": None,
        "cvss_score": None,
        "severity": None,
        "description": "No CVE assigned",
        "references": [],
        "published_date": None,
    }

    vulnerability = normalize_zdi_advisory(raw)

    assert vulnerability.advisory_id == "ZDI-CAN-99999"
    assert vulnerability.aliases == []


def test_parse_zdi_search_results_extracts_detail_links():
    html = '''
    <html><body>
      <a href="/advisories/ZDI-25-001/">ZDI-25-001</a>
      <a href="/advisories/ZDI-CAN-12345/">ZDI-CAN-12345</a>
    </body></html>
    '''

    assert parse_zdi_search_results(html) == [
        "https://www.zerodayinitiative.com/advisories/ZDI-25-001/",
        "https://www.zerodayinitiative.com/advisories/ZDI-CAN-12345/",
    ]


def test_zdi_source_returns_empty_when_search_has_no_links():
    class FakeResponse:
        text = "<html><body>No advisories</body></html>"

        def raise_for_status(self):
            return None

    def fake_get(url, params=None, timeout=30):
        return FakeResponse()

    source = ZdiSource(get=fake_get)

    assert source.search(Target(name="Adobe Reader"), "Adobe Reader") == []
