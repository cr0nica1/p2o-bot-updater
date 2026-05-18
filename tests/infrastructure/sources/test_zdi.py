from updater.domain.models import Target
from updater.infrastructure.sources.zdi import (
    ZdiSource,
    normalize_zdi_advisory,
    parse_zdi_detail,
    parse_zdi_search_results,
)


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


def test_zdi_source_skips_bad_detail_page_and_returns_valid_result():
    class FakeResponse:
        def __init__(self, text, *, raises=False):
            self.text = text
            self._raises = raises

        def raise_for_status(self):
            if self._raises:
                raise RuntimeError("bad detail page")
            return None

    search_html = '''
    <html><body>
      <a href="/advisories/ZDI-25-001/">ZDI-25-001</a>
      <a href="/advisories/ZDI-25-002/">ZDI-25-002</a>
    </body></html>
    '''
    valid_detail_html = '''
    <html><body>
      <h1>ZDI-25-002 CVE-2025-2222</h1>
      <p>CVSS: 8.8</p>
      <p>Severity: High</p>
      <p>Published: 2025-02-03</p>
      <p>Description: Valid advisory</p>
    </body></html>
    '''

    def fake_get(url, params=None, timeout=30):
        if params is not None:
            return FakeResponse(search_html)
        if url.endswith("/ZDI-25-001/"):
            return FakeResponse("", raises=True)
        return FakeResponse(valid_detail_html)

    source = ZdiSource(get=fake_get)

    results = source.search(Target(name="Adobe Reader"), "Adobe Reader")

    assert len(results) == 1
    vulnerability, evidence = results[0]
    assert vulnerability.advisory_id == "CVE-2025-2222"
    assert evidence["url"] == "https://www.zerodayinitiative.com/advisories/ZDI-25-002/"


def test_parse_zdi_detail_ignores_invalid_cvss_score():
    html = '''
    <html><body>
      <h1>ZDI-25-099 CVE-2025-9999</h1>
      <p>CVSS: 99</p>
      <p>Severity: Critical</p>
      <p>Description: Invalid CVSS score</p>
    </body></html>
    '''

    raw = parse_zdi_detail(html, "https://www.zerodayinitiative.com/advisories/ZDI-25-099/")

    assert raw["cvss_score"] is None
