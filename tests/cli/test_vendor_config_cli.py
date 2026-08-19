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


def test_seed_passes_version_repo(monkeypatch, capsys):
    captured = {}

    class FakeConfig:
        mongodb_uri = "mongodb://localhost:27017"
        mongodb_database = "pwn2own_updater"

    class FakeDB:
        def __init__(self, *a, **k):
            self.db = object()

    def fake_seed(target_repo, vendor_repo, version_repo=None):
        captured["version_repo"] = version_repo
        captured["target_repo"] = type(target_repo).__name__
        captured["vendor_repo"] = type(vendor_repo).__name__
        return {"targets": 11, "configs": 10}

    monkeypatch.setattr("updater.cli.vendor_config.load_config", lambda path: FakeConfig())
    monkeypatch.setattr("updater.infrastructure.mongo.MongoDatabase", FakeDB)
    monkeypatch.setattr("updater.infrastructure.mongo.MongoTargetRepository", lambda db: type("T", (), {})())
    monkeypatch.setattr("updater.infrastructure.mongo.MongoVendorConfigRepository", lambda db: type("V", (), {})())
    monkeypatch.setattr("updater.infrastructure.mongo.MongoTargetVersionRepository", lambda db: type("Ver", (), {"kind": "version"})())
    # seed is imported inside the seed branch — patch the module attribute
    import updater.infrastructure.seed.version_checks as seed_mod
    monkeypatch.setattr(seed_mod, "seed", fake_seed)

    code = main(["seed"])
    assert code == 0
    assert captured["version_repo"] is not None
    assert "Seeded 11 targets and 10 version checks." in capsys.readouterr().out


def test_purge_chroma_prints_counts(monkeypatch, capsys):
    class Result:
        unlinked = 17
        deleted_vulnerabilities = 17

    class FakeConfig:
        mongodb_uri = "mongodb://localhost:27017"
        mongodb_database = "pwn2own_updater"

    class FakeDB:
        def __init__(self, *a, **k):
            self.db = object()

    class FakeService:
        def __init__(self, *a, **k):
            pass
        def run(self):
            return Result()

    monkeypatch.setattr("updater.cli.vendor_config.load_config", lambda path: FakeConfig())
    monkeypatch.setattr("updater.infrastructure.mongo.MongoDatabase", FakeDB)
    monkeypatch.setattr("updater.infrastructure.mongo.MongoTargetRepository", lambda db: object())
    monkeypatch.setattr("updater.infrastructure.mongo.MongoVulnerabilityRepository", lambda db: object())
    monkeypatch.setattr("updater.infrastructure.mongo.MongoTargetVulnerabilityRepository", lambda db: object())
    monkeypatch.setattr("updater.application.purge_chroma.PurgeChromaService", FakeService)

    code = main(["purge-chroma"])
    assert code == 0
    out = capsys.readouterr().out
    assert "unlinked=17" in out
    assert "deleted_vulnerabilities=17" in out
