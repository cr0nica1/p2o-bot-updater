from updater.domain.models import Target
from updater.infrastructure.sources.zdi import (
    ZDI_ADVISORIES_URL,
    ZdiSource,
    normalize_zdi_advisory,
    parse_zdi_detail,
    parse_zdi_published_rows,
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


def test_parse_zdi_published_rows_extracts_structured_advisories():
    html = '''
    <html><body>
    <table>
      <tr>
        <td><a href="/advisories/ZDI-26-280/">ZDI-26-280</a></td>
        <td>ZDI-CAN-28366</td>
        <td>HP</td>
        <td>CVE-2026-4682</td>
        <td>8.8</td>
        <td>2026-04-15</td>
        <td>2026-04-15</td>
        <td>(Pwn2Own) HP DeskJet 2855e JobStatusEvent Stack-based Buffer Overflow Remote Code Execution Vulnerability</td>
      </tr>
      <tr>
        <td><a href="/advisories/ZDI-26-275/">ZDI-26-275</a></td>
        <td>ZDI-CAN-27212</td>
        <td>Microsoft</td>
        <td></td>
        <td>8.8</td>
        <td>2026-04-15</td>
        <td>2026-04-15</td>
        <td>Microsoft Qlib _mount_nfs_uri Command Injection Remote Code Execution Vulnerability</td>
      </tr>
    </table>
    </body></html>
    '''

    rows = parse_zdi_published_rows(html)

    assert len(rows) == 2

    assert rows[0]["zdi_id"] == "ZDI-26-280"
    assert rows[0]["zdi_can_id"] == "ZDI-CAN-28366"
    assert rows[0]["vendor"] == "HP"
    assert rows[0]["cve_id"] == "CVE-2026-4682"
    assert rows[0]["cvss_score"] == 8.8
    assert rows[0]["published_date"] == "2026-04-15"
    assert rows[0]["description"] == "(Pwn2Own) HP DeskJet 2855e JobStatusEvent Stack-based Buffer Overflow Remote Code Execution Vulnerability"
    assert rows[0]["detail_url"] == "https://www.zerodayinitiative.com/advisories/ZDI-26-280/"

    assert rows[1]["zdi_id"] == "ZDI-26-275"
    assert rows[1]["cve_id"] is None
    assert rows[1]["cvss_score"] == 8.8


def test_parse_zdi_published_rows_uses_null_references_without_link():
    html = '''
    <html><body>
    <table>
      <tr>
        <td>ZDI-26-280</td>
        <td>ZDI-CAN-28366</td>
        <td>HP</td>
        <td>CVE-2026-4682</td>
        <td>8.8</td>
        <td>2026-04-15</td>
        <td>2026-04-15</td>
        <td>Valid row without link</td>
      </tr>
    </table>
    </body></html>
    '''

    rows = parse_zdi_published_rows(html)

    assert rows[0]["references"] is None
    assert rows[0]["detail_url"] is None


def test_normalize_zdi_advisory_allows_null_references():
    raw = {
        "zdi_id": "ZDI-26-280",
        "cve_id": None,
        "cvss_score": 8.8,
        "severity": "High",
        "description": "Valid row without link",
        "references": None,
        "published_date": "2026-04-15",
    }

    vulnerability = normalize_zdi_advisory(raw)

    assert vulnerability.references == []


def test_parse_zdi_published_rows_skips_rows_without_zdi_id():
    html = '''
    <html><body>
    <table>
      <tr>
        <td><a href="/advisories/ZDI-26-280/">ZDI-26-280</a></td>
        <td>ZDI-CAN-28366</td>
        <td>HP</td>
        <td>CVE-2026-4682</td>
        <td>8.8</td>
        <td>2026-04-15</td>
        <td>2026-04-15</td>
        <td>Valid row</td>
      </tr>
      <tr>
        <td>Header</td>
        <td>Column</td>
        <td>Names</td>
        <td>Here</td>
        <td>9.0</td>
        <td></td>
        <td></td>
        <td>Not an advisory</td>
      </tr>
    </table>
    </body></html>
    '''

    rows = parse_zdi_published_rows(html)

    assert len(rows) == 1
    assert rows[0]["zdi_id"] == "ZDI-26-280"


def test_parse_zdi_published_rows_returns_empty_for_no_table():
    html = "<html><body>No table here</body></html>"

    assert parse_zdi_published_rows(html) == []


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


def test_zdi_source_fetches_published_advisory_years_since_2020():
    requested_urls = []

    class FakeResponse:
        text = "<html><body>No advisories</body></html>"

        def raise_for_status(self):
            return None

    def fake_get(url, params=None, timeout=30):
        requested_urls.append(url)
        return FakeResponse()

    source = ZdiSource(get=fake_get)

    assert source.search(Target(name="Adobe Reader"), "Adobe Reader") == []
    assert ZDI_ADVISORIES_URL == "https://www.zerodayinitiative.com/advisories/published/"
    assert requested_urls == [
        "https://www.zerodayinitiative.com/advisories/published/2020/",
        "https://www.zerodayinitiative.com/advisories/published/2021/",
        "https://www.zerodayinitiative.com/advisories/published/2022/",
        "https://www.zerodayinitiative.com/advisories/published/2023/",
        "https://www.zerodayinitiative.com/advisories/published/2024/",
        "https://www.zerodayinitiative.com/advisories/published/2025/",
        "https://www.zerodayinitiative.com/advisories/published/2026/",
    ]


def test_zdi_source_fetches_published_advisory_years_from_since_year():
    requested_urls = []

    class FakeResponse:
        text = "<html><body>No advisories</body></html>"

        def raise_for_status(self):
            return None

    def fake_get(url, params=None, timeout=30):
        requested_urls.append(url)
        return FakeResponse()

    source = ZdiSource(get=fake_get)

    assert source.search(Target(name="Adobe Reader"), "Adobe Reader", since_year=2026) == []
    assert requested_urls == [
        "https://www.zerodayinitiative.com/advisories/published/2026/",
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


def test_zdi_source_includes_published_rows_with_cve_id():
    table_html = '''
    <html><body>
    <table>
      <tr>
        <td><a href="/advisories/ZDI-26-280/">ZDI-26-280</a></td>
        <td>ZDI-CAN-28366</td>
        <td>HP</td>
        <td>CVE-2026-4682</td>
        <td>8.8</td>
        <td>2026-04-15</td>
        <td>2026-04-15</td>
        <td>HP DeskJet vulnerability</td>
      </tr>
      <tr>
        <td><a href="/advisories/ZDI-26-281/">ZDI-26-281</a></td>
        <td>ZDI-CAN-28367</td>
        <td>HP</td>
        <td></td>
        <td>7.5</td>
        <td>2026-04-15</td>
        <td>2026-04-15</td>
        <td>HP OfficeJet vulnerability without CVE</td>
      </tr>
    </table>
    </body></html>
    '''
    empty_html = "<html><body><table></table></body></html>"

    class FakeResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    def fake_get(url, params=None, timeout=30):
        return FakeResponse(table_html if "2026" in url else empty_html)

    source = ZdiSource(get=fake_get)

    results = source.search(Target(name="HP"), "HP")

    assert len(results) == 2
    advisory_ids = [vuln.advisory_id for vuln, _ in results]
    assert "CVE-2026-4682" in advisory_ids
    assert "ZDI-26-281" in advisory_ids


def test_zdi_source_uses_detail_page_description_for_published_rows():
    table_html = '''
    <html><body>
    <table>
      <tr>
        <td><a href="/advisories/ZDI-26-280/">ZDI-26-280</a></td>
        <td>ZDI-CAN-28366</td>
        <td>HP</td>
        <td>CVE-2026-4682</td>
        <td>8.8</td>
        <td>2026-04-15</td>
        <td>2026-04-15</td>
        <td>Published table description</td>
      </tr>
    </table>
    </body></html>
    '''
    detail_html = '''
    <html><head>
      <meta name="description" content="Overall page summary">
    </head><body>
      <h1>ZDI-26-280 CVE-2026-4682</h1>
      <table>
        <tr>
          <td>VULNERABILITY DETAILS</td>
          <td>Vulnerability details row description</td>
        </tr>
      </table>
    </body></html>
    '''

    class FakeResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    def fake_get(url, params=None, timeout=30):
        if url == f"{ZDI_ADVISORIES_URL}2026/":
            return FakeResponse(table_html)
        if url.startswith(ZDI_ADVISORIES_URL):
            return FakeResponse("<html><body>No advisories</body></html>")
        return FakeResponse(detail_html)

    source = ZdiSource(get=fake_get)

    results = source.search(Target(name="HP"), "HP", since_year=2026)

    vulnerability, evidence = results[0]
    assert vulnerability.description == "Vulnerability details row description"
    assert evidence["zdi"]["description"] == "Vulnerability details row description"



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
      <h1>ZDI-25-002</h1>
      <p>CVSS: 8.8</p>
      <p>Severity: High</p>
      <p>Published: 2025-02-03</p>
      <p>Description: Valid advisory</p>
    </body></html>
    '''

    def fake_get(url, params=None, timeout=30):
        if url == f"{ZDI_ADVISORIES_URL}2025/":
            return FakeResponse(search_html)
        if url.startswith(ZDI_ADVISORIES_URL):
            return FakeResponse("<html><body>No advisories</body></html>")
        if url.endswith("/ZDI-25-001/"):
            return FakeResponse("", raises=True)
        return FakeResponse(valid_detail_html)

    source = ZdiSource(get=fake_get)

    results = source.search(Target(name="Adobe Reader"), "Adobe Reader")

    assert len(results) == 1
    vulnerability, evidence = results[0]
    assert vulnerability.advisory_id == "ZDI-25-002"
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
