from updater.domain.models import Target
from updater.infrastructure.sources.nvd import NvdSource, normalize_nvd_item, strip_cpe_from_raw, strip_non_english_descriptions, strip_non_nist_cvss_metrics


def test_normalize_nvd_item_extracts_required_fields_with_nvd_2_references():
    raw = {
        "cve": {
            "id": "CVE-2025-1234",
            "published": "2025-01-02T03:04:05.000",
            "descriptions": [{"lang": "en", "value": "Example vulnerability"}],
            "references": [
                {"url": "https://example.test/ref"},
                {"url": ""},
                {},
            ],
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


def test_normalize_nvd_item_extracts_legacy_reference_data():
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

    assert vulnerability.references == ["https://example.test/ref"]


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


def test_strip_cpe_from_raw_removes_configurations():
    raw = {
        "cve": {
            "id": "CVE-2025-1234",
            "configurations": [
                {
                    "nodes": [
                        {
                            "cpeMatch": [
                                {"criteria": "cpe:2.3:a:adobe:acrobat_reader:*:*:*:*:*:*:*:*", "vulnerable": True}
                            ]
                        }
                    ]
                }
            ],
        }
    }

    cleaned = strip_cpe_from_raw(raw)

    assert "configurations" not in cleaned["cve"]
    assert "configurations" in raw["cve"]


def test_nvd_source_evidence_excludes_cpe_configurations():
    raw = {
        "cve": {
            "id": "CVE-2025-1234",
            "published": "2025-01-02T03:04:05.000",
            "descriptions": [{"lang": "en", "value": "Example"}],
            "references": [],
            "metrics": {
                "cvssMetricV31": [{"cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL"}}]
            },
            "configurations": [
                {
                    "nodes": [
                        {
                            "cpeMatch": [
                                {"criteria": "cpe:2.3:a:adobe:acrobat_reader:*:*:*:*:*:*:*:*", "vulnerable": True}
                            ]
                        }
                    ]
                }
            ],
        }
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"vulnerabilities": [raw]}

    def fake_get(url, **kwargs):
        return FakeResponse()

    source = NvdSource(get=fake_get)
    results = source.search(Target(name="Adobe Reader"), "Adobe Reader")

    assert len(results) == 1
    vulnerability, evidence = results[0]
    assert "configurations" not in vulnerability.raw["nvd"]["cve"]
    assert "configurations" not in evidence["nvd"]["cve"]


def test_strip_non_nist_cvss_metrics_keeps_only_nist():
    raw = {
        "cve": {
            "id": "CVE-2025-1234",
            "metrics": {
                "cvssMetricV31": [
                    {"source": "psirt@cisco.com", "cvssData": {"baseScore": 9.1, "baseSeverity": "CRITICAL"}, "type": "Secondary"},
                    {"source": "nvd@nist.gov", "cvssData": {"baseScore": 8.8, "baseSeverity": "HIGH"}, "type": "Primary"},
                ],
                "cvssMetricV2": [
                    {"source": "psirt@cisco.com", "cvssData": {"baseScore": 6.8}, "type": "Secondary"},
                ],
            },
        }
    }

    cleaned = strip_non_nist_cvss_metrics(raw)

    v31 = cleaned["cve"]["metrics"]["cvssMetricV31"]
    assert len(v31) == 1
    assert v31[0]["source"] == "nvd@nist.gov"
    assert "cvssMetricV2" not in cleaned["cve"]["metrics"]


def test_normalize_nvd_prefers_nist_cvss_over_third_party():
    raw = {
        "cve": {
            "id": "CVE-2025-1234",
            "published": "2025-01-02T03:04:05.000",
            "descriptions": [{"lang": "en", "value": "Example"}],
            "references": [],
            "metrics": {
                "cvssMetricV31": [
                    {"source": "psirt@cisco.com", "cvssData": {"baseScore": 9.1, "baseSeverity": "CRITICAL"}},
                    {"source": "nvd@nist.gov", "cvssData": {"baseScore": 8.8, "baseSeverity": "HIGH"}},
                ],
            },
        }
    }

    vulnerability = normalize_nvd_item(raw)

    assert vulnerability.cvss_score == 8.8
    assert vulnerability.severity == "high"
    # raw also stripped non-NIST entries
    assert len(vulnerability.raw["nvd"]["cve"]["metrics"]["cvssMetricV31"]) == 1


def test_normalize_nvd_falls_back_to_cna_when_nist_absent():
    raw = {
        "cve": {
            "id": "CVE-2026-54592",
            "published": "2026-07-10T00:00:00.000",
            "descriptions": [{"lang": "en", "value": "CNA-only advisory"}],
            "references": [],
            "metrics": {
                "cvssMetricV31": [
                    {
                        "source": "security-advisories@github.com",
                        "type": "Secondary",
                        "cvssData": {"baseScore": 7.5, "baseSeverity": "HIGH"},
                    }
                ],
            },
        }
    }

    vulnerability = normalize_nvd_item(raw)

    assert vulnerability.cvss_score == 7.5
    assert vulnerability.severity == "high"
    # CNA metrics are preserved in raw as the fallback source of truth.
    assert vulnerability.raw["nvd"]["cve"]["metrics"]["cvssMetricV31"][0]["source"] == "security-advisories@github.com"


def test_normalize_nvd_reads_cvss_v40_cna_score():
    raw = {
        "cve": {
            "id": "CVE-2026-54502",
            "published": "2026-07-10T00:00:00.000",
            "descriptions": [{"lang": "en", "value": "CVSS v4.0 advisory"}],
            "references": [],
            "metrics": {
                "cvssMetricV40": [
                    {
                        "source": "security-advisories@github.com",
                        "type": "Secondary",
                        "cvssData": {"version": "4.0", "baseScore": 6.3, "baseSeverity": "MEDIUM"},
                    }
                ],
            },
        }
    }

    vulnerability = normalize_nvd_item(raw)

    assert vulnerability.cvss_score == 6.3
    assert vulnerability.severity == "medium"


def test_strip_keeps_cna_metrics_when_no_nist_score():
    raw = {
        "cve": {
            "id": "CVE-2026-54592",
            "metrics": {
                "cvssMetricV31": [
                    {"source": "security-advisories@github.com", "cvssData": {"baseScore": 7.5, "baseSeverity": "HIGH"}, "type": "Secondary"},
                ],
            },
        }
    }

    cleaned = strip_non_nist_cvss_metrics(raw)

    assert cleaned["cve"]["metrics"]["cvssMetricV31"][0]["source"] == "security-advisories@github.com"


def test_strip_non_english_descriptions_from_raw():
    raw = {
        "cve": {
            "id": "CVE-2025-1234",
            "descriptions": [
                {"lang": "en", "value": "Buffer overflow in Adobe Reader"},
                {"lang": "es", "value": "Desbordamiento de búfer en Adobe Reader"},
                {"lang": "fr", "value": "Dépassement de mémoire tampon dans Adobe Reader"},
                {"lang": "ja", "value": "Adobe Reader のバッファオーバーフロー"},
            ],
        }
    }

    cleaned = strip_non_english_descriptions(raw)

    descs = cleaned["cve"]["descriptions"]
    assert len(descs) == 1
    assert descs[0]["lang"] == "en"
    assert descs[0]["value"] == "Buffer overflow in Adobe Reader"


def test_normalize_nvd_item_strips_non_english_from_raw():
    raw = {
        "cve": {
            "id": "CVE-2025-1234",
            "published": "2025-01-02T03:04:05.000",
            "descriptions": [
                {"lang": "en", "value": "English description"},
                {"lang": "es", "value": "Spanish description"},
            ],
            "references": [],
            "metrics": {
                "cvssMetricV31": [{"cvssData": {"baseScore": 7.5, "baseSeverity": "HIGH"}}]
            },
        }
    }

    vulnerability = normalize_nvd_item(raw)

    assert vulnerability.description == "English description"
    raw_descs = vulnerability.raw["nvd"]["cve"]["descriptions"]
    assert len(raw_descs) == 1
    assert raw_descs[0]["lang"] == "en"


def test_nvd_source_builds_query_request(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"vulnerabilities": []}

    def fake_get(url, **kwargs):
        calls.append({
            "url": url,
            "params": kwargs.get("params"),
            "timeout": kwargs.get("timeout"),
            "headers": kwargs.get("headers"),
        })
        return FakeResponse()

    source = NvdSource(get=fake_get)

    result = source.search(Target(name="Adobe Acrobat Reader"), "Adobe Reader", since_year=2026)

    assert result == []
    assert calls[0]["url"] == "https://services.nvd.nist.gov/rest/json/cves/2.0"
    assert calls[0]["params"]["keywordSearch"] == "Adobe Reader"
    assert calls[0]["params"]["keywordExactMatch"] == ""
    assert calls[0]["params"]["pubStartDate"] == "2026-01-01T00:00:00.000"
    assert "apiKey" not in calls[0]["params"]
    assert calls[0]["timeout"] == 30


def test_nvd_source_sends_api_key_as_header():
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"vulnerabilities": []}

    def fake_get(url, **kwargs):
        calls.append(kwargs)
        return FakeResponse()

    source = NvdSource(get=fake_get, api_key="test-secret-key")
    result = source.search(Target(name="Adobe Acrobat Reader"), "Adobe Reader")

    assert result == []
    assert calls[0]["headers"] == {"apiKey": "test-secret-key"}
    assert "apiKey" not in calls[0]["params"]


from datetime import date

from updater.infrastructure.sources.nvd import NvdSource, nvd_pub_windows


def test_nvd_pub_windows_splits_into_120_day_chunks():
    windows = nvd_pub_windows(2026, today=date(2026, 8, 19))
    assert windows == [
        ("2026-01-01T00:00:00.000", "2026-04-30T23:59:59.999"),
        ("2026-05-01T00:00:00.000", "2026-08-19T23:59:59.999"),
    ]


def test_nvd_pub_windows_empty_when_year_in_future():
    assert nvd_pub_windows(2027, today=date(2026, 8, 19)) == []


def test_nvd_search_without_since_year_omits_dates():
    captured = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"vulnerabilities": []}

    def fake_get(url, **kwargs):
        captured.append(kwargs.get("params"))
        return FakeResponse()

    NvdSource(get=fake_get).search(Target(name="LiteLLM"), "LiteLLM")
    assert "pubStartDate" not in captured[0]
    assert "pubEndDate" not in captured[0]


def test_nvd_search_with_since_year_sends_start_and_end_per_window():
    captured = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"vulnerabilities": []}

    def fake_get(url, **kwargs):
        captured.append(kwargs.get("params"))
        return FakeResponse()

    NvdSource(get=fake_get).search(
        Target(name="LiteLLM"), "LiteLLM", since_year=2026, today=date(2026, 8, 19)
    )
    assert len(captured) == 2
    assert captured[0]["pubStartDate"] == "2026-01-01T00:00:00.000"
    assert captured[0]["pubEndDate"] == "2026-04-30T23:59:59.999"
    assert captured[1]["pubStartDate"] == "2026-05-01T00:00:00.000"
    assert captured[1]["pubEndDate"] == "2026-08-19T23:59:59.999"
    assert captured[0]["keywordSearch"] == "LiteLLM"
    assert "keywordExactMatch" in captured[0]
