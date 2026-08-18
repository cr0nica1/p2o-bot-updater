from updater.application.firmware_lookup import FirmwareLookupError, FirmwareLookupResult
from updater.application.version_scan import (
    VersionChange,
    VersionScanService,
    version_changes_from_docs,
)
from updater.domain.models import Target, TargetVersion, VendorConfig


class FakeTargetRepo:
    def __init__(self, targets):
        self._targets = list(targets)

    def list_all(self):
        return list(self._targets)


class FakeVendorConfigRepo:
    def __init__(self, bound_names):
        self._bound = set(bound_names)

    def find_by_target(self, target):
        if target.name in self._bound:
            return VendorConfig(vendor=target.name, target=target.name,
                                url_template="https://x/releases", fetch="http",
                                regex=r"v(\d+\.\d+\.\d+)", select="first")
        return None


class FakeVersionRepo:
    def __init__(self, latest=None):
        self.latest = dict(latest or {})   # storage_id -> TargetVersion
        self.marked = []
        self.set_calls = []

    def find_latest(self, target_id):
        return self.latest.get(target_id)

    def set_current(self, target_id, *, version, source_url, previous_version):
        tv = TargetVersion(target_id=target_id, version=version, source_url=source_url,
                           previous_version=previous_version, is_latest=True)
        self.latest[target_id] = tv
        self.set_calls.append((target_id, version, previous_version))
        return tv

    def mark_seen(self, target_id, *, version):
        self.marked.append((target_id, version))


class FakeLookup:
    """lookup(target_id) -> result or raises, keyed by 1-based sorted index."""

    def __init__(self, by_id):
        self.by_id = by_id

    def lookup(self, target_id):
        outcome = self.by_id[target_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _result(version, url="https://x/releases"):
    return FirmwareLookupResult(target_name="", vendor="", resolved_url=url,
                                version=version, download_url=None, html_snippet="")


def test_first_scan_seeds_silently():
    targets = [Target(name="Chroma", id="c1")]
    repo = FakeVersionRepo()
    service = VersionScanService(FakeTargetRepo(targets), FakeVendorConfigRepo({"Chroma"}),
                                 repo, FakeLookup({1: _result("1.6.0")}))
    report = service.scan_all()
    assert report.changes == []
    assert report.seeded == ["Chroma"]
    assert repo.latest["c1"].version == "1.6.0"
    assert repo.latest["c1"].previous_version is None


def test_changed_version_is_reported_and_persisted():
    targets = [Target(name="Chroma", id="c1")]
    repo = FakeVersionRepo(latest={"c1": TargetVersion(target_id="c1", version="1.5.9")})
    service = VersionScanService(FakeTargetRepo(targets), FakeVendorConfigRepo({"Chroma"}),
                                 repo, FakeLookup({1: _result("1.6.0")}))
    report = service.scan_all()
    assert report.changes == [VersionChange("Chroma", "1.5.9", "1.6.0", "https://x/releases")]
    assert repo.set_calls == [("c1", "1.6.0", "1.5.9")]


def test_unchanged_version_marks_seen():
    targets = [Target(name="Chroma", id="c1")]
    repo = FakeVersionRepo(latest={"c1": TargetVersion(target_id="c1", version="1.6.0")})
    service = VersionScanService(FakeTargetRepo(targets), FakeVendorConfigRepo({"Chroma"}),
                                 repo, FakeLookup({1: _result("1.6.0")}))
    report = service.scan_all()
    assert report.unchanged == ["Chroma"]
    assert report.changes == []
    assert repo.marked == [("c1", "1.6.0")]


def test_lookup_error_is_isolated_and_others_still_scan():
    # sorted by casefold: "Alpha" (id=1), "Zeta" (id=2)
    targets = [Target(name="Zeta", id="z1"), Target(name="Alpha", id="a1")]
    repo = FakeVersionRepo()
    lookup = FakeLookup({1: FirmwareLookupError("boom"), 2: _result("2.0.0")})
    service = VersionScanService(FakeTargetRepo(targets), FakeVendorConfigRepo({"Alpha", "Zeta"}),
                                 repo, lookup)
    report = service.scan_all()
    assert report.errors == [("Alpha", "boom")]
    assert report.seeded == ["Zeta"]


def test_targets_without_bound_config_are_skipped():
    targets = [Target(name="Chroma", id="c1"), Target(name="Legacy", id="l1")]
    repo = FakeVersionRepo()
    service = VersionScanService(FakeTargetRepo(targets), FakeVendorConfigRepo({"Chroma"}),
                                 repo, FakeLookup({1: _result("1.6.0")}))
    report = service.scan_all()
    assert report.seeded == ["Chroma"]
    assert "Legacy" not in report.seeded + report.unchanged


def test_version_changes_from_docs_resolves_names_and_skips_unknown():
    targets = [Target(name="Chroma", id="c1")]
    docs = [
        TargetVersion(target_id="c1", version="1.6.0", previous_version="1.5.9", source_url="u"),
        TargetVersion(target_id="ghost", version="9.9", previous_version="9.8", source_url="u"),
    ]
    changes = version_changes_from_docs(docs, targets)
    assert changes == [VersionChange("Chroma", "1.5.9", "1.6.0", "u")]


def test_notify_window_start_is_24h_lookback():
    from datetime import datetime, timezone
    from updater.application.version_scan import notify_window_start
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    # 24h back, NOT start-of-day (which would be 2026-08-18 00:00 and would drop
    # a change first-seen the previous evening).
    assert notify_window_start(now) == datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)
