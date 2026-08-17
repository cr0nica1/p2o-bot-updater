from updater.cli.vendor_config import main
from updater.domain.models import VendorConfig


class FakeRepo:
    def __init__(self):
        self.configs = {}
        self.deleted = []

    def upsert(self, config):
        self.configs[config.normalized_vendor] = config
        return config

    def list_all(self):
        return list(self.configs.values())

    def delete(self, vendor):
        self.deleted.append(vendor)
        return self.configs.pop(vendor.strip().lower(), None) is not None


def test_vendor_config_add_validates_and_saves(capsys):
    repo = FakeRepo()

    code = main(
        [
            "add",
            "--vendor",
            "Canon",
            "--url-template",
            "https://vendor.example/{alias}",
            "--attr-id",
            "firmware",
            "--regex",
            r"Version ([^<]+).*href=\"([^\"]+)\"",
        ],
        repo=repo,
    )

    assert code == 0
    assert repo.configs["canon"].vendor == "Canon"
    assert "Saved vendor config: Canon" in capsys.readouterr().out


def test_vendor_config_add_rejects_invalid_regex(capsys):
    repo = FakeRepo()
    code = main(
        ["add", "--vendor", "Canon", "--url-template", "https://vendor.example/{alias}",
         "--attr-id", "firmware", "--regex", "(unbalanced"],
        repo=repo,
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "Vendor regex is invalid" in captured.err
    assert repo.configs == {}


def test_vendor_config_add_target_bound_http(capsys):
    repo = FakeRepo()
    code = main(
        ["add", "--vendor", "Chroma", "--target", "Chroma",
         "--url-template", "https://github.com/chroma-core/chroma/releases",
         "--fetch", "http", "--select", "first",
         "--regex", r'releases/tag/(\d+\.\d+\.\d+)(?=["/#?])'],
        repo=repo,
    )
    assert code == 0
    saved = repo.configs["chroma"]
    assert saved.target == "Chroma"
    assert saved.fetch == "http"
    assert saved.attr_id == ""
    assert "Saved vendor config: Chroma" in capsys.readouterr().out


def test_vendor_config_list_prints_configs(capsys):
    repo = FakeRepo()
    repo.upsert(
        VendorConfig(
            vendor="Canon",
            url_template="https://vendor.example/{alias}",
            attr_id="firmware",
            regex="(.+) (.+)",
        )
    )

    code = main(["list"], repo=repo)

    assert code == 0
    assert "Canon" in capsys.readouterr().out


def test_vendor_config_remove_deletes_config(capsys):
    repo = FakeRepo()
    repo.upsert(
        VendorConfig(
            vendor="Canon",
            url_template="https://vendor.example/{alias}",
            attr_id="firmware",
            regex="(.+) (.+)",
        )
    )

    code = main(["remove", "--vendor", "Canon"], repo=repo)

    assert code == 0
    assert repo.configs == {}
    assert "Removed vendor config: Canon" in capsys.readouterr().out
