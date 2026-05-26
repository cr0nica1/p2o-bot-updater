from updater.application.firmware_lookup import FirmwareLookupError, FirmwareLookupResult
from updater.cli import firmware_lookup


class FakeService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def lookup(self, target_id):
        self.calls.append(("lookup", target_id))
        if self.error is not None:
            raise self.error
        return self.result

    def lookup_with_inputs(self, *, target_id, url_template, attr_id, regex):
        self.calls.append(("lookup_with_inputs", target_id, url_template, attr_id, regex))
        if self.error is not None:
            raise self.error
        return self.result


def test_firmware_lookup_cli_prints_result(capsys):
    service = FakeService(
        FirmwareLookupResult(
            target_name="Canon MF654Cdw",
            vendor="Canon",
            resolved_url="https://vendor.example/downloads/canon-mf654cdw/firmware",
            version="2.1.0",
            download_url="https://vendor.example/files/fw.bin",
            html_snippet='<a href="/files/fw.bin">Version 2.1.0</a>',
        )
    )

    code = firmware_lookup.main(["--target-id", "2"], service=service)

    output = capsys.readouterr().out
    assert code == 0
    assert service.calls == [("lookup", 2)]
    assert "Target: Canon MF654Cdw" in output
    assert "Vendor: Canon" in output
    assert "Firmware Version: 2.1.0" in output
    assert "Download URL: https://vendor.example/files/fw.bin" in output


def test_firmware_lookup_cli_uses_runtime_inputs(capsys):
    service = FakeService(
        FirmwareLookupResult(
            target_name="TP-Link Archer C6",
            vendor="TP-Link",
            resolved_url="https://www.tp-link.com/uk/support/download/archer-c6/v4/#Firmware",
            version="Archer C6(EU)_V4_1.13.7 Build 240515",
            download_url="https://static.tp-link.com/fw.zip",
            html_snippet='<a href="https://static.tp-link.com/fw.zip">Archer C6(EU)_V4_1.13.7 Build 240515</a>',
        )
    )

    code = firmware_lookup.main(
        [
            "--target-id",
            "1",
            "--url-template",
            "https://www.tp-link.com/uk/support/download/{alias}/#Firmware",
            "--attr-id",
            "tabpanel-Firmware",
            "--regex",
            r"(Archer C6\(EU\)_V4_[^<]+).*href=\"([^\"]+)\"",
        ],
        service=service,
    )

    output = capsys.readouterr().out
    assert code == 0
    assert service.calls == [
        (
            "lookup_with_inputs",
            1,
            "https://www.tp-link.com/uk/support/download/{alias}/#Firmware",
            "tabpanel-Firmware",
            r"(Archer C6\(EU\)_V4_[^<]+).*href=\"([^\"]+)\"",
        )
    ]
    assert "Firmware Version: Archer C6(EU)_V4_1.13.7 Build 240515" in output


def test_firmware_lookup_cli_prints_errors(capsys):
    service = FakeService(error=FirmwareLookupError("No firmware vendor config found for Canon."))

    code = firmware_lookup.main(["--target-id", "1"], service=service)

    captured = capsys.readouterr()
    assert code == 2
    assert "No firmware vendor config found for Canon." in captured.err
