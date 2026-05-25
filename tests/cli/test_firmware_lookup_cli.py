from updater.application.firmware_lookup import FirmwareLookupError, FirmwareLookupResult
from updater.cli import firmware_lookup


class FakeService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def lookup(self, target_id):
        self.calls.append(target_id)
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
    assert service.calls == [2]
    assert "Target: Canon MF654Cdw" in output
    assert "Vendor: Canon" in output
    assert "Firmware Version: 2.1.0" in output
    assert "Download URL: https://vendor.example/files/fw.bin" in output


def test_firmware_lookup_cli_prints_errors(capsys):
    service = FakeService(error=FirmwareLookupError("No firmware vendor config found for Canon."))

    code = firmware_lookup.main(["--target-id", "1"], service=service)

    captured = capsys.readouterr()
    assert code == 2
    assert "No firmware vendor config found for Canon." in captured.err
