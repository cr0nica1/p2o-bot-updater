import pytest

from updater.application.firmware_lookup import (
    FirmwareLookupError,
    FirmwareLookupService,
    validate_vendor_config,
)
from updater.domain.models import Target, VendorConfig


class FakeTargetRepository:
    def __init__(self, targets):
        self.targets = list(targets)

    def list_all(self):
        return list(self.targets)


class FakeVendorConfigRepository:
    def __init__(self, configs):
        self.configs = {config.normalized_vendor: config for config in configs}

    def find_by_vendor(self, vendor):
        from updater.domain.models import normalize_name

        return self.configs.get(normalize_name(vendor))


class FakeBrowser:
    def __init__(self, html):
        self.html = html
        self.calls = []

    def fetch_element_html(self, url, element_id):
        self.calls.append((url, element_id))
        return self.html


def _service(targets, configs, html):
    return FirmwareLookupService(
        target_repo=FakeTargetRepository(targets),
        vendor_config_repo=FakeVendorConfigRepository(configs),
        browser=FakeBrowser(html),
    )


def test_lookup_resolves_target_id_using_sorted_list_and_extracts_version_and_url():
    target_a = Target(name="Zebra", vendor="Other", vendor_alias="zebra")
    target_b = Target(name="Canon MF654Cdw", vendor="Canon", vendor_alias="canon-mf654cdw")
    config = VendorConfig(
        vendor="Canon",
        url_template="https://vendor.example/downloads/{alias}/firmware",
        attr_id="firmware",
        regex=r"(?=.*Version ([^<]+)).*href=\"([^\"]+)\"",
    )
    service = _service(
        [target_a, target_b],
        [config],
        '<a href="/files/fw-2.1.0.bin">Version 2.1.0</a>',
    )

    result = service.lookup(1)

    assert result.target_name == "Canon MF654Cdw"
    assert result.vendor == "Canon"
    assert result.resolved_url == "https://vendor.example/downloads/canon-mf654cdw/firmware"
    assert result.version == "2.1.0"
    assert result.download_url == "https://vendor.example/files/fw-2.1.0.bin"
    assert result.html_snippet == '<a href="/files/fw-2.1.0.bin">Version 2.1.0</a>'


def test_lookup_url_encodes_vendor_alias():
    target = Target(name="Camera", vendor="Canon", vendor_alias="model x")
    config = VendorConfig(
        vendor="Canon",
        url_template="https://vendor.example/downloads/{alias}",
        attr_id="firmware",
        regex=r"(?=.*Version ([^<]+)).*href=\"([^\"]+)\"",
    )
    browser = FakeBrowser('<a href="https://vendor.example/fw.bin">Version 1.0</a>')
    service = FirmwareLookupService(
        target_repo=FakeTargetRepository([target]),
        vendor_config_repo=FakeVendorConfigRepository([config]),
        browser=browser,
    )

    service.lookup(1)

    assert browser.calls == [("https://vendor.example/downloads/model%20x", "firmware")]


def test_lookup_preserves_slashes_in_vendor_alias_path_segments():
    target = Target(name="TP-Link Archer C6", vendor="TP-Link", vendor_alias="archer-c6/v4")
    config = VendorConfig(
        vendor="TP-Link",
        url_template="https://www.tp-link.com/uk/support/download/{alias}/#Firmware",
        attr_id="Firmware",
        regex=r"(?=.*Version ([^<]+)).*href=\"([^\"]+)\"",
    )
    browser = FakeBrowser('<a href="https://static.tp-link.com/fw.zip">Version 1.0</a>')
    service = FirmwareLookupService(
        target_repo=FakeTargetRepository([target]),
        vendor_config_repo=FakeVendorConfigRepository([config]),
        browser=browser,
    )

    service.lookup(1)

    assert browser.calls == [("https://www.tp-link.com/uk/support/download/archer-c6/v4/#Firmware", "Firmware")]


def test_lookup_with_inputs_uses_runtime_url_attr_and_regex():
    target = Target(name="TP-Link Archer C6", vendor="TP-Link", vendor_alias="archer-c6/v4")
    browser = FakeBrowser('<span>Archer C6(EU)_V4_1.13.7 Build 240515</span><a href="firmware.zip">Download</a>')
    service = FirmwareLookupService(
        target_repo=FakeTargetRepository([target]),
        vendor_config_repo=FakeVendorConfigRepository([]),
        browser=browser,
    )

    result = service.lookup_with_inputs(
        target_id=1,
        url_template="https://www.tp-link.com/uk/support/download/{alias}/#Firmware",
        attr_id="tabpanel-Firmware",
        regex=r"(Archer C6\(EU\)_V4_[^<]+)[\s\S]*href=\"([^\"]+)\"",
    )

    assert browser.calls == [("https://www.tp-link.com/uk/support/download/archer-c6/v4/#Firmware", "tabpanel-Firmware")]
    assert result.target_name == "TP-Link Archer C6"
    assert result.vendor == "TP-Link"
    assert result.version == "Archer C6(EU)_V4_1.13.7 Build 240515"
    assert result.download_url == "https://www.tp-link.com/uk/support/download/archer-c6/v4/firmware.zip"


@pytest.mark.parametrize(
    "target_id,message",
    [
        (0, "Invalid target ID"),
        (2, "Invalid target ID"),
    ],
)
def test_lookup_rejects_invalid_target_id(target_id, message):
    service = _service([Target(name="Canon", vendor="Canon", vendor_alias="canon")], [], "")

    with pytest.raises(FirmwareLookupError, match=message):
        service.lookup(target_id)


def test_lookup_rejects_target_without_vendor():
    service = _service([Target(name="Canon", vendor_alias="canon")], [], "")

    with pytest.raises(FirmwareLookupError, match="Target 'Canon' has no vendor"):
        service.lookup(1)


def test_lookup_rejects_target_without_vendor_alias():
    service = _service([Target(name="Canon", vendor="Canon")], [], "")

    with pytest.raises(FirmwareLookupError, match="vendor_alias"):
        service.lookup(1)


def test_lookup_rejects_missing_vendor_config():
    service = _service([Target(name="Canon", vendor="Canon", vendor_alias="canon")], [], "")

    with pytest.raises(FirmwareLookupError, match="No firmware vendor config found for Canon"):
        service.lookup(1)


def test_lookup_rejects_regex_without_match():
    target = Target(name="Canon", vendor="Canon", vendor_alias="canon")
    config = VendorConfig(
        vendor="Canon",
        url_template="https://vendor.example/{alias}",
        attr_id="firmware",
        regex="Firmware ([0-9.]+) href='([^']+)'",
    )
    service = _service([target], [config], "no firmware here")

    with pytest.raises(FirmwareLookupError, match="Regex did not match"):
        service.lookup(1)


def test_lookup_rejects_non_https_download_url():
    target = Target(name="Canon", vendor="Canon", vendor_alias="canon")
    config = VendorConfig(
        vendor="Canon",
        url_template="https://vendor.example/{alias}",
        attr_id="firmware",
        regex=r"(?=.*Version ([^<]+)).*href=\"([^\"]+)\"",
    )
    service = _service([target], [config], '<a href="http://vendor.example/fw.bin">Version 1.0</a>')

    with pytest.raises(FirmwareLookupError, match="download URL must be relative or HTTPS"):
        service.lookup(1)


def test_validate_vendor_config_rejects_bad_config():
    with pytest.raises(FirmwareLookupError, match="HTTPS"):
        validate_vendor_config(
            VendorConfig(vendor="Canon", url_template="http://vendor.example/{alias}", attr_id="firmware", regex="(.+) (.+)")
        )

    with pytest.raises(FirmwareLookupError, match=r"\{alias\}"):
        validate_vendor_config(
            VendorConfig(vendor="Canon", url_template="https://vendor.example/downloads", attr_id="firmware", regex="(.+) (.+)")
        )

    with pytest.raises(FirmwareLookupError, match="at least two capture groups"):
        validate_vendor_config(
            VendorConfig(vendor="Canon", url_template="https://vendor.example/{alias}", attr_id="firmware", regex="(.+)")
        )
