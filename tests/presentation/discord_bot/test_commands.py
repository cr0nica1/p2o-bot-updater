from datetime import datetime, timezone

from updater.domain.models import Target, TargetVulnerability, VendorConfig, Vulnerability
from updater.presentation.discord_bot.commands import (
    CommandResult,
    Services,
    handle_add_target,
    handle_add_vuln,
    handle_clear_database,
    handle_import_targets,
    handle_import_vendor_firmware,
    handle_list_targets,
    handle_lookup_firmware,
    handle_remove_target,
    handle_scan_versions,
    handle_search_vulns,
    handle_set_schedule,
    handle_set_vendor_alias,
    handle_set_vendor_firmware,
    handle_show_schedule,
    handle_show_target,
    handle_sync_cves,
)


class FakeTargetRepo:
    def __init__(self, targets=None):
        self._targets = list(targets or [])

    def upsert(self, target):
        target.id = target.id or f"target-{len(self._targets) + 1}"
        self._targets.append(target)
        return target

    def list_all(self):
        return list(self._targets)

    def find_by_name(self, name):
        norm = name.strip().lower()
        return next((t for t in self._targets if t.name.lower() == norm), None)

    def delete(self, name):
        norm = name.strip().lower()
        for i, t in enumerate(self._targets):
            if t.name.lower() == norm:
                self._targets.pop(i)
                return True
        return False

    def delete_all(self):
        deleted = len(self._targets)
        self._targets.clear()
        return deleted


class FakeVersionRepo:
    def __init__(self, latest=None):
        self.calls = []
        self.latest = dict(latest or {})

    def upsert(self, version):
        self.calls.append(version)
        return version

    def delete_all(self):
        deleted = len(self.calls)
        self.calls.clear()
        return deleted

    def find_latest(self, target_id):
        return self.latest.get(target_id)

    def set_current(self, target_id, *, version, source_url, previous_version):
        from updater.domain.models import TargetVersion
        tv = TargetVersion(target_id=target_id, version=version, source_url=source_url,
                           previous_version=previous_version, is_latest=True)
        self.latest[target_id] = tv
        return tv

    def mark_seen(self, target_id, *, version):
        pass


class FakeVulnRepo:
    def __init__(self, items=None):
        self.items = {v.advisory_id: v for v in (items or [])}

    def upsert(self, vuln):
        vuln.id = vuln.id or vuln.advisory_id
        self.items[vuln.advisory_id] = vuln
        return vuln

    def list_all(self):
        return list(self.items.values())

    def delete(self, vulnerability_id):
        for advisory_id, vulnerability in list(self.items.items()):
            if vulnerability.id == vulnerability_id or vulnerability.advisory_id == vulnerability_id:
                del self.items[advisory_id]
                return True
        return False

    def delete_all(self):
        deleted = len(self.items)
        self.items.clear()
        return deleted


class FakeLinkRepo:
    def __init__(self, links=None):
        self.links = list(links or [])

    def upsert(self, link):
        link.id = link.id or f"link-{len(self.links) + 1}"
        self.links.append(link)
        return link

    def list_all(self):
        return list(self.links)

    def delete_by_target(self, target_id):
        before = len(self.links)
        self.links = [link for link in self.links if link.target_id != target_id]
        return before - len(self.links)

    def delete_all(self):
        deleted = len(self.links)
        self.links.clear()
        return deleted


class FakeVendorConfigRepo:
    def __init__(self, configs=None):
        self.configs = {c.vendor: c for c in (configs or [])}

    def upsert(self, config):
        self.configs[config.vendor] = config
        return config

    def find_by_vendor(self, vendor):
        from updater.domain.models import normalize_name
        norm = normalize_name(vendor)
        return next((c for c in self.configs.values() if c.normalized_vendor == norm), None)

    def find_by_target(self, target):
        from updater.domain.models import normalize_name
        norm = normalize_name(target.name)
        return next(
            (c for c in self.configs.values() if c.normalized_target == norm), None
        )

    def list_all(self):
        return list(self.configs.values())

    def delete(self, vendor):
        from updater.domain.models import normalize_name
        norm = normalize_name(vendor)
        for key in list(self.configs):
            if normalize_name(key) == norm:
                del self.configs[key]
                return True
        return False


class FakeBrowserAdapter:
    def __init__(self, html="<span>v1.0</span><a href='https://example.com/fw.bin'>download</a>"):
        self.html = html
        self.calls = []

    def fetch_element_html(self, url, element_id):
        self.calls.append({"url": url, "element_id": element_id})
        return self.html


class FakeHttpAdapter:
    def __init__(self, html="v1.0.0"):
        self.html = html
        self.calls = []

    def fetch_html(self, url, selector=None):
        self.calls.append((url, selector))
        return self.html


def _services(target_repo=None, vuln_repo=None, link_repo=None, version_repo=None, sources=None, vendor_config_repo=None, browser=None, http=None):
    return Services(
        target_repo=target_repo or FakeTargetRepo(),
        version_repo=version_repo or FakeVersionRepo(),
        vulnerability_repo=vuln_repo or FakeVulnRepo(),
        target_vulnerability_repo=link_repo or FakeLinkRepo(),
        sources=sources or [],
        vendor_config_repo=vendor_config_repo or FakeVendorConfigRepo(),
        browser=browser or FakeBrowserAdapter(),
        http=http or FakeHttpAdapter(),
    )


def test_services_includes_vendor_config_repo_and_browser():
    services = _services()
    assert services.vendor_config_repo is not None
    assert services.browser is not None


async def test_list_targets_empty():
    result = await handle_list_targets(_services())
    assert isinstance(result, CommandResult)
    assert "No targets" in result.text


async def test_list_targets_returns_numbered_names_sorted_alphabetically():
    services = _services(target_repo=FakeTargetRepo([
        Target(id="t2", name="Canon MF654Cdw"),
        Target(id="t1", name="Adobe Reader"),
    ]))
    result = await handle_list_targets(services)
    assert result.text == "Targets:\n1. Adobe Reader\n2. Canon MF654Cdw"


async def test_show_target_resolves_numbered_target_id_from_sorted_list():
    target = Target(id="t1", name="Adobe Reader", aliases=["Acrobat"], vendor="Adobe", category="pdf")
    services = _services(target_repo=FakeTargetRepo([
        Target(id="t2", name="Canon MF654Cdw"),
        target,
    ]))
    result = await handle_show_target(services, target_id=1, limit=None)
    assert result.text.splitlines()[:5] == [
        "Target #1: Adobe Reader",
        "Aliases: Acrobat",
        "Vendor: Adobe",
        "Category: pdf",
        "No vulnerabilities found.",
    ]
    assert result.embeds == []


async def test_show_target_rejects_out_of_range_target_id():
    services = _services(target_repo=FakeTargetRepo([Target(id="t1", name="Adobe Reader")]))
    result = await handle_show_target(services, target_id=2, limit=None)
    assert result.text == "Invalid target ID. Use /list-targets to see available targets (1-1)."
    assert result.ephemeral is True


async def test_show_target_returns_vulnerability_embeds_sorted_by_recent_date():
    old = Vulnerability(
        id="v-old",
        advisory_id="CVE-2024-0001",
        severity="LOW",
        description="old bug",
        published_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    new = Vulnerability(
        id="v-new",
        advisory_id="CVE-2024-0002",
        severity="HIGH",
        description="new bug",
        published_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
    )
    target = Target(id="t1", name="Canon")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vuln_repo=FakeVulnRepo([old, new]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="v-old"),
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="v-new"),
        ]),
    )

    result = await handle_show_target(services, target_id=1, limit=None)

    assert "Showing 2 of 2 vulnerabilities" in result.text
    assert [embed.title for embed in result.embeds] == ["CVE-2024-0002", "CVE-2024-0001"]


async def test_show_target_limit_shows_only_most_recent_vulnerabilities():
    target = Target(id="t1", name="Canon")
    newest = Vulnerability(
        id="v-newest",
        advisory_id="CVE-2024-0003",
        created_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
    )
    middle = Vulnerability(
        id="v-middle",
        advisory_id="CVE-2024-0002",
        created_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
    )
    oldest = Vulnerability(
        id="v-oldest",
        advisory_id="CVE-2024-0001",
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vuln_repo=FakeVulnRepo([oldest, newest, middle]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="v-oldest"),
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="v-newest"),
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="v-middle"),
        ]),
    )

    result = await handle_show_target(services, target_id=1, limit=2)

    assert "Showing 2 of 3 vulnerabilities" in result.text
    assert [embed.title for embed in result.embeds] == ["CVE-2024-0003", "CVE-2024-0002"]


async def test_add_target_creates_target():
    services = _services()
    result = await handle_add_target(
        services,
        name="Adobe Reader",
        aliases=["Acrobat"],
        vendor="Adobe",
        category="pdf",
    )
    assert "Added" in result.text
    saved = services.target_repo.list_all()
    assert saved[0].name == "Adobe Reader"
    assert saved[0].aliases == ["Acrobat"]
    assert saved[0].vendor == "Adobe"
    assert saved[0].category == "pdf"


async def test_add_target_accepts_vendor_alias():
    services = _services()
    result = await handle_add_target(
        services,
        name="Canon MF654Cdw",
        vendor="Canon",
        vendor_alias="canon-mf654cdw",
    )
    assert "Canon MF654Cdw" in result.text
    target = services.target_repo.find_by_name("Canon MF654Cdw")
    assert target.vendor_alias == "canon-mf654cdw"


async def test_remove_target_removes_target_and_links():
    target = Target(id="t1", name="Adobe Reader")
    vulnerability = Vulnerability(id="v1", advisory_id="CVE-2024-0001")
    link = TargetVulnerability(target_id="t1", vulnerability_id="v1")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vuln_repo=FakeVulnRepo([vulnerability]),
        link_repo=FakeLinkRepo([link]),
    )
    result = await handle_remove_target(services, names=["Adobe Reader"])
    assert "Removed" in result.text
    assert services.target_repo.list_all() == []
    assert services.target_vulnerability_repo.list_all() == []
    assert services.vulnerability_repo.list_all() == []


async def test_remove_target_preserves_vulnerability_linked_to_other_target():
    removed_target = Target(id="t1", name="Adobe Reader")
    kept_target = Target(id="t2", name="Canon")
    vulnerability = Vulnerability(id="v1", advisory_id="CVE-2024-0001")
    services = _services(
        target_repo=FakeTargetRepo([removed_target, kept_target]),
        vuln_repo=FakeVulnRepo([vulnerability]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", vulnerability_id="v1"),
            TargetVulnerability(target_id="t2", vulnerability_id="v1"),
        ]),
    )

    result = await handle_remove_target(services, names=["Adobe Reader"])

    assert "Removed" in result.text
    assert [target.name for target in services.target_repo.list_all()] == ["Canon"]
    assert services.vulnerability_repo.list_all() == [vulnerability]
    assert [
        (link.target_id, link.vulnerability_id)
        for link in services.target_vulnerability_repo.list_all()
    ] == [("t2", "v1")]


async def test_remove_multiple_targets_deletes_vulnerability_linked_only_to_removed_targets():
    target_a = Target(id="t1", name="Adobe Reader")
    target_b = Target(id="t2", name="Acrobat")
    vulnerability = Vulnerability(id="v1", advisory_id="CVE-2024-0001")
    services = _services(
        target_repo=FakeTargetRepo([target_a, target_b]),
        vuln_repo=FakeVulnRepo([vulnerability]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", vulnerability_id="v1"),
            TargetVulnerability(target_id="t2", vulnerability_id="v1"),
        ]),
    )

    result = await handle_remove_target(services, names=["Adobe Reader", "Acrobat"])

    assert "Removed" in result.text
    assert services.target_repo.list_all() == []
    assert services.target_vulnerability_repo.list_all() == []
    assert services.vulnerability_repo.list_all() == []


async def test_remove_target_reports_missing():
    services = _services()
    result = await handle_remove_target(services, names=["Adobe Reader"])
    assert "not found" in result.text.lower()


async def test_clear_database_rejects_missing_confirmation():
    services = _services(
        target_repo=FakeTargetRepo([Target(id="t1", name="Canon")]),
        vuln_repo=FakeVulnRepo([Vulnerability(advisory_id="CVE-2024-1")]),
        link_repo=FakeLinkRepo([TargetVulnerability(target_id="t1", vulnerability_id="CVE-2024-1")]),
    )
    services.version_repo.upsert(object())

    result = await handle_clear_database(services, confirm="delete")

    assert "type DELETE" in result.text
    assert result.ephemeral is True
    assert len(services.target_repo.list_all()) == 1
    assert len(services.version_repo.calls) == 1
    assert len(services.vulnerability_repo.list_all()) == 1
    assert len(services.target_vulnerability_repo.list_all()) == 1


async def test_clear_database_deletes_all_data_and_reports_counts():
    services = _services(
        target_repo=FakeTargetRepo([Target(id="t1", name="Canon"), Target(id="t2", name="Adobe")]),
        vuln_repo=FakeVulnRepo([Vulnerability(advisory_id="CVE-2024-1")]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", vulnerability_id="CVE-2024-1"),
            TargetVulnerability(target_id="t2", vulnerability_id="CVE-2024-1"),
        ]),
    )
    services.version_repo.upsert(object())
    services.version_repo.upsert(object())
    services.version_repo.upsert(object())

    result = await handle_clear_database(services, confirm="DELETE")

    assert result.ephemeral is True
    assert "Database cleared." in result.text
    assert "targets=2" in result.text
    assert "versions=3" in result.text
    assert "vulnerabilities=1" in result.text
    assert "links=2" in result.text
    assert services.target_repo.list_all() == []
    assert services.version_repo.calls == []
    assert services.vulnerability_repo.list_all() == []
    assert services.target_vulnerability_repo.list_all() == []


async def test_import_targets_imports_csv_bytes():
    csv_text = "name,aliases,vendor\nAdobe Reader,Acrobat,Adobe\n"
    services = _services()
    result = await handle_import_targets(services, csv_bytes=csv_text.encode())
    assert "imported" in result.text.lower()
    assert services.target_repo.list_all()[0].name == "Adobe Reader"


async def test_add_vuln_without_target_creates_vulnerability_only():
    services = _services()
    result = await handle_add_vuln(
        services,
        advisory_id="CVE-2024-12647",
        description="boom",
        cvss_score=7.8,
        severity="HIGH",
        references=["https://x"],
        target_name=None,
    )
    assert "Added" in result.text
    assert services.vulnerability_repo.list_all()[0].advisory_id == "CVE-2024-12647"
    assert services.target_vulnerability_repo.list_all() == []


async def test_add_vuln_with_target_creates_link():
    services = _services(target_repo=FakeTargetRepo([Target(id="t1", name="Canon")]))
    result = await handle_add_vuln(
        services,
        advisory_id="CVE-2024-12647",
        description="boom",
        cvss_score=7.8,
        severity="HIGH",
        references=[],
        target_name="Canon",
    )
    assert "Added" in result.text
    assert services.target_vulnerability_repo.list_all()[0].target_id == "t1"


async def test_add_vuln_with_unknown_target_returns_error():
    services = _services()
    result = await handle_add_vuln(
        services,
        advisory_id="CVE-1",
        description="",
        cvss_score=None,
        severity=None,
        references=[],
        target_name="Nope",
    )
    assert "not found" in result.text.lower()
    assert services.vulnerability_repo.list_all() == []


class _FakeSource:
    source_name = "fake"

    def search(self, target, query, since_year=None):
        if query == "Canon":
            return [(
                Vulnerability(advisory_id="CVE-2024-1", sources=["fake"], severity="HIGH", description="d"),
                {"matched": query},
            )]
        return []


class _StaticSource:
    source_name = "fake"

    def __init__(self, findings):
        self.findings = findings

    def search(self, target, query, since_year=None):
        if query != "Canon":
            return []
        return [(vulnerability, {"matched": query}) for vulnerability in self.findings]


class _PreservingVulnRepo(FakeVulnRepo):
    def upsert(self, vuln):
        existing = self.items.get(vuln.advisory_id)
        if existing is not None:
            vuln.created_at = existing.created_at
        return super().upsert(vuln)


async def test_sync_cves_returns_embeds_for_findings():
    target = Target(id="t1", name="Canon")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        sources=[_FakeSource()],
    )
    result = await handle_sync_cves(services, target_name="Canon")
    assert any("Sync" in line for line in result.text.splitlines())
    assert len(result.embeds) == 1
    assert result.embeds[0].title == "CVE-2024-1"


async def test_sync_cves_unknown_target_returns_not_found():
    services = _services(sources=[_FakeSource()])
    result = await handle_sync_cves(services, target_name="Unknown")
    assert "not found" in result.text.lower()
    assert result.embeds == []


def test_filter_findings_to_created_since_keeps_only_new_vulnerabilities():
    from updater.presentation.discord_bot.commands import filter_findings_to_created_since

    sync_started_at = datetime(2026, 5, 21, 13, 34, 0, tzinfo=timezone.utc)
    old = Vulnerability(
        advisory_id="CVE-2024-0001",
        created_at=datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc),
    )
    fresh = Vulnerability(
        advisory_id="CVE-2024-0002",
        created_at=datetime(2026, 5, 21, 13, 34, 30, tzinfo=timezone.utc),
    )
    findings = [
        {"advisory_id": "CVE-2024-0001", "target_names": ["Canon"]},
        {"advisory_id": "CVE-2024-0002", "target_names": ["Canon"]},
    ]

    filtered = filter_findings_to_created_since(
        findings,
        [old, fresh],
        sync_started_at,
    )

    assert [finding["advisory_id"] for finding in filtered] == ["CVE-2024-0002"]


def test_filter_findings_to_created_since_handles_mongo_naive_utc_datetimes():
    from updater.presentation.discord_bot.commands import filter_findings_to_created_since

    sync_started_at = datetime(2026, 5, 21, 13, 34, 0, tzinfo=timezone.utc)
    old = Vulnerability(
        advisory_id="CVE-2024-0001",
        created_at=datetime(2026, 5, 21, 12, 0),
    )
    fresh = Vulnerability(
        advisory_id="CVE-2024-0002",
        created_at=datetime(2026, 5, 21, 13, 34, 30),
    )
    findings = [
        {"advisory_id": "CVE-2024-0001", "target_names": ["Canon"]},
        {"advisory_id": "CVE-2024-0002", "target_names": ["Canon"]},
    ]

    filtered = filter_findings_to_created_since(
        findings,
        [old, fresh],
        sync_started_at,
    )

    assert [finding["advisory_id"] for finding in filtered] == ["CVE-2024-0002"]


async def test_sync_cves_only_reports_vulnerabilities_stored_since_sync_minute():
    from unittest.mock import patch

    existing = Vulnerability(
        advisory_id="CVE-2024-0001",
        severity="LOW",
        description="old bug already in db",
        created_at=datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc),
    )
    fresh = Vulnerability(
        advisory_id="CVE-2024-0002",
        severity="HIGH",
        description="new bug from this sync",
        created_at=datetime(2026, 5, 21, 13, 34, 30, tzinfo=timezone.utc),
    )
    target = Target(id="t1", name="Canon")
    source = _StaticSource([existing, fresh])

    services = _services(
        target_repo=FakeTargetRepo([target]),
        vuln_repo=_PreservingVulnRepo([existing]),
        sources=[source],
    )

    sync_start = datetime(2026, 5, 21, 13, 34, 0, tzinfo=timezone.utc)
    with patch("updater.presentation.discord_bot.commands.datetime") as mock_dt:
        mock_dt.now.return_value = sync_start
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await handle_sync_cves(services, target_name="Canon")

    assert len(result.embeds) == 1
    assert result.embeds[0].title == "CVE-2024-0002"


async def test_set_schedule_writes_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=tok\nSYNC_TIME=08:00\nNOTIFY_TIME=09:00\n")
    result = await handle_set_schedule(
        env_path=env_file,
        sync_time="10:15",
        notify_time="11:30",
    )
    assert "10:15" in result.text
    assert "11:30" in result.text
    assert "SYNC_TIME=10:15" in env_file.read_text()


async def test_set_schedule_rejects_invalid(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=tok\n")
    result = await handle_set_schedule(
        env_path=env_file,
        sync_time="25:00",
        notify_time="09:00",
    )
    assert "invalid" in result.text.lower()


async def test_show_schedule_displays_current_times():
    result = await handle_show_schedule(sync_time=(8, 0), notify_time=(9, 30))
    assert "08:00" in result.text
    assert "09:30" in result.text


async def test_search_vulns_year_matches_cve_id_year():
    vuln_2024 = Vulnerability(
        advisory_id="CVE-2024-12647",
        severity="HIGH",
        description="canon bug",
        created_at=datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc),
    )
    vuln_2023 = Vulnerability(
        advisory_id="CVE-2023-9999",
        severity="LOW",
        description="old bug",
        created_at=datetime(2026, 5, 21, 11, 0, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([vuln_2024, vuln_2023]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="CVE-2024-12647"),
            TargetVulnerability(target_id="t2", target_name="Other", vulnerability_id="CVE-2023-9999"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        severity=None,
        year=2024,
        from_date="2026-05-21",
        to_date="2026-05-21",
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert "Found 1 vulnerabilities" in result.text
    assert len(result.embeds) == 1
    assert result.embeds[0].title == "CVE-2024-12647"


async def test_search_vulns_year_matches_zdi_short_year():
    vuln = Vulnerability(
        advisory_id="ZDI-24-280",
        severity="MEDIUM",
        description="zdi bug",
        created_at=datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([vuln]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="ZDI-24-280"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        severity=None,
        year=2024,
        from_date="2026-05-21",
        to_date="2026-05-21",
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert len(result.embeds) == 1
    assert result.embeds[0].title == "ZDI-24-280"


async def test_search_vulns_year_matches_published_date_year():
    vuln = Vulnerability(
        advisory_id="VENDOR-ABC",
        severity="HIGH",
        description="vendor advisory",
        published_date=datetime(2024, 9, 10, tzinfo=timezone.utc),
        created_at=datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([vuln]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Vendor", vulnerability_id="VENDOR-ABC"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        severity=None,
        year=2024,
        from_date="2026-05-21",
        to_date="2026-05-21",
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert len(result.embeds) == 1
    assert result.embeds[0].title == "VENDOR-ABC"


async def test_search_vulns_filters_created_at_date_range():
    in_range = Vulnerability(
        advisory_id="CVE-2024-1111",
        created_at=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
    )
    out_of_range = Vulnerability(
        advisory_id="CVE-2024-2222",
        created_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([in_range, out_of_range]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="In", vulnerability_id="CVE-2024-1111"),
            TargetVulnerability(target_id="t2", target_name="Out", vulnerability_id="CVE-2024-2222"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        severity=None,
        year=None,
        from_date="2026-05-19",
        to_date="2026-05-21",
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert len(result.embeds) == 1
    assert result.embeds[0].title == "CVE-2024-1111"


async def test_search_vulns_defaults_to_today_when_no_dates_given():
    today_vuln = Vulnerability(
        advisory_id="CVE-2024-1111",
        created_at=datetime(2026, 5, 21, 1, 0, tzinfo=timezone.utc),
    )
    yesterday_vuln = Vulnerability(
        advisory_id="CVE-2024-2222",
        created_at=datetime(2026, 5, 20, 16, 59, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([today_vuln, yesterday_vuln]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Today", vulnerability_id="CVE-2024-1111"),
            TargetVulnerability(target_id="t2", target_name="Yesterday", vulnerability_id="CVE-2024-2222"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        severity=None,
        year=None,
        from_date=None,
        to_date=None,
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert len(result.embeds) == 1
    assert result.embeds[0].title == "CVE-2024-1111"
    assert "collected: 2026-05-21 to 2026-05-21" in result.text


async def test_search_vulns_defaults_to_today_uses_utc_plus_7_date():
    local_today_vuln = Vulnerability(
        advisory_id="CVE-2024-1111",
        created_at=datetime(2026, 5, 20, 18, 0, tzinfo=timezone.utc),
    )
    local_yesterday_vuln = Vulnerability(
        advisory_id="CVE-2024-2222",
        created_at=datetime(2026, 5, 20, 16, 59, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([local_today_vuln, local_yesterday_vuln]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Today", vulnerability_id="CVE-2024-1111"),
            TargetVulnerability(target_id="t2", target_name="Yesterday", vulnerability_id="CVE-2024-2222"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        severity=None,
        year=None,
        from_date=None,
        to_date=None,
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert len(result.embeds) == 1
    assert result.embeds[0].title == "CVE-2024-1111"


async def test_search_vulns_applies_year_and_date_with_and_logic():
    matching = Vulnerability(
        advisory_id="CVE-2024-1111",
        created_at=datetime(2026, 5, 21, 1, 0, tzinfo=timezone.utc),
    )
    wrong_year = Vulnerability(
        advisory_id="CVE-2023-2222",
        created_at=datetime(2026, 5, 21, 1, 0, tzinfo=timezone.utc),
    )
    wrong_date = Vulnerability(
        advisory_id="CVE-2024-3333",
        created_at=datetime(2026, 5, 19, 1, 0, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([matching, wrong_year, wrong_date]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Match", vulnerability_id="CVE-2024-1111"),
            TargetVulnerability(target_id="t2", target_name="WrongYear", vulnerability_id="CVE-2023-2222"),
            TargetVulnerability(target_id="t3", target_name="WrongDate", vulnerability_id="CVE-2024-3333"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        severity=None,
        year=2024,
        from_date="2026-05-21",
        to_date="2026-05-21",
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert len(result.embeds) == 1
    assert result.embeds[0].title == "CVE-2024-1111"


async def test_search_vulns_returns_no_results_message():
    services = _services(vuln_repo=FakeVulnRepo([]), link_repo=FakeLinkRepo([]))

    result = await handle_search_vulns(
        services,
        severity=None,
        year=2024,
        from_date="2026-05-21",
        to_date="2026-05-21",
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert result.text == "No vulnerabilities found matching the filters."
    assert result.embeds == []


async def test_search_vulns_rejects_invalid_date():
    result = await handle_search_vulns(
        _services(),
        severity=None,
        year=None,
        from_date="2026/05/21",
        to_date=None,
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert "YYYY-MM-DD" in result.text
    assert result.ephemeral is True


async def test_search_vulns_rejects_out_of_range_year():
    result = await handle_search_vulns(
        _services(),
        severity=None,
        year=1998,
        from_date=None,
        to_date=None,
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert "year" in result.text.lower()
    assert result.ephemeral is True


async def test_search_vulns_severity_only_searches_entire_database():
    old_high = Vulnerability(
        advisory_id="CVE-2024-0001",
        severity="HIGH",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    new_low = Vulnerability(
        advisory_id="CVE-2024-0002",
        severity="LOW",
        created_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )
    new_high = Vulnerability(
        advisory_id="CVE-2024-0003",
        severity="HIGH",
        created_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([old_high, new_low, new_high]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="A", vulnerability_id="CVE-2024-0001"),
            TargetVulnerability(target_id="t2", target_name="B", vulnerability_id="CVE-2024-0002"),
            TargetVulnerability(target_id="t3", target_name="C", vulnerability_id="CVE-2024-0003"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        severity="HIGH",
        year=None,
        from_date=None,
        to_date=None,
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert "severity: HIGH" in result.text
    assert "scope: all" in result.text
    assert len(result.embeds) == 2


async def test_search_vulns_severity_with_date_filter():
    high_1 = Vulnerability(
        advisory_id="CVE-2024-0001",
        severity="HIGH",
        created_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )
    high_2 = Vulnerability(
        advisory_id="CVE-2024-0002",
        severity="HIGH",
        created_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )
    low = Vulnerability(
        advisory_id="CVE-2024-0003",
        severity="LOW",
        created_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([high_1, high_2, low]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="A", vulnerability_id="CVE-2024-0001"),
            TargetVulnerability(target_id="t2", target_name="B", vulnerability_id="CVE-2024-0002"),
            TargetVulnerability(target_id="t3", target_name="C", vulnerability_id="CVE-2024-0003"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        severity="HIGH",
        year=None,
        from_date="2026-05-21",
        to_date="2026-05-21",
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert len(result.embeds) == 1
    assert result.embeds[0].title == "CVE-2024-0002"
    assert "severity: HIGH" in result.text
    assert "collected: 2026-05-21 to 2026-05-21" in result.text


async def test_search_vulns_severity_with_year_filter():
    vuln_2024 = Vulnerability(
        advisory_id="CVE-2024-0001",
        severity="MEDIUM",
        created_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )
    old_vuln_2024 = Vulnerability(
        advisory_id="CVE-2024-0004",
        severity="MEDIUM",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    vuln_2023 = Vulnerability(
        advisory_id="CVE-2023-0002",
        severity="MEDIUM",
        created_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([vuln_2024, old_vuln_2024, vuln_2023]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="A", vulnerability_id="CVE-2024-0001"),
            TargetVulnerability(target_id="t2", target_name="B", vulnerability_id="CVE-2024-0004"),
            TargetVulnerability(target_id="t3", target_name="C", vulnerability_id="CVE-2023-0002"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        severity="MEDIUM",
        year=2024,
        from_date=None,
        to_date=None,
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert len(result.embeds) == 2
    assert {embed.title for embed in result.embeds} == {"CVE-2024-0001", "CVE-2024-0004"}
    assert "severity: MEDIUM" in result.text
    assert "year: 2024" in result.text
    assert "collected:" not in result.text


async def test_search_vulns_rejects_invalid_severity():
    services = _services()

    result = await handle_search_vulns(
        services,
        severity="URGENT",
        year=None,
        from_date=None,
        to_date=None,
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert result.ephemeral is True
    assert "CRITICAL" in result.text
    assert "HIGH" in result.text


def test_bot_module_exposes_main_and_build_client():
    from updater.presentation.discord_bot import bot

    assert callable(bot.main)
    assert callable(bot.build_client)


def test_show_target_command_uses_target_id_and_limit_options(tmp_path):
    from pathlib import Path
    from unittest.mock import patch

    from discord import app_commands
    from updater.presentation.discord_bot.bot import build_client
    from updater.presentation.discord_bot.config import BotConfig, UTC_PLUS_7

    config = BotConfig(
        env_path=Path(tmp_path / ".env"),
        discord_token="token",
        guild_id=1,
        channel_id=2,
        admin_role_id=3,
        sync_time=(8, 0),
        notify_time=(9, 0),
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="test",
        tz=UTC_PLUS_7,
    )
    original_tree = app_commands.CommandTree
    captured = {}

    def capture_tree(client):
        tree = original_tree(client)
        captured["tree"] = tree
        return tree

    with (
        patch("updater.presentation.discord_bot.bot.app_commands.CommandTree", side_effect=capture_tree),
        patch("updater.presentation.discord_bot.bot._build_services", return_value=_services()),
    ):
        build_client(config)

    guild_commands = captured["tree"]._guild_commands[1]
    show_target = guild_commands["show-target"]

    assert [parameter.name for parameter in show_target.parameters] == ["target_id", "limit"]


def test_chunk_embeds_splits_in_batches_of_ten():
    from updater.presentation.discord_bot.bot import _chunk_embeds

    chunks = list(_chunk_embeds([object() for _ in range(23)], size=10))

    assert [len(chunk) for chunk in chunks] == [10, 10, 3]


def test_local_to_utc_converts_utc_plus_7_time():
    from datetime import timedelta, timezone

    from updater.presentation.discord_bot.bot import _local_to_utc

    assert _local_to_utc(8, 30, timezone(timedelta(hours=7))) == (1, 30)


async def test_resolve_channel_fetches_when_cache_misses():
    from updater.presentation.discord_bot.bot import _resolve_channel

    class FakeClient:
        def __init__(self):
            self.fetched_id = None

        def get_channel(self, channel_id):
            return None

        async def fetch_channel(self, channel_id):
            self.fetched_id = channel_id
            return "channel"

    client = FakeClient()

    result = await _resolve_channel(client, 123)

    assert result == "channel"
    assert client.fetched_id == 123


async def test_send_command_result_sends_embed_batches_without_interaction_followup():
    import discord

    from updater.presentation.discord_bot.bot import _send_command_result
    from updater.presentation.discord_bot.commands import CommandResult

    calls = []

    async def send(**kwargs):
        calls.append(kwargs)

    embeds = [discord.Embed(title=f"Finding {index}") for index in range(11)]
    await _send_command_result(send, CommandResult(text="Sync complete", embeds=embeds))

    assert calls[0]["content"] == "Sync complete — showing 1-10 of 11"
    assert len(calls[0]["embeds"]) == 10
    assert calls[1]["content"] == "Showing 11-11 of 11"
    assert len(calls[1]["embeds"]) == 1


async def test_send_command_result_sends_text_when_no_embeds():
    from updater.presentation.discord_bot.bot import _send_command_result
    from updater.presentation.discord_bot.commands import CommandResult

    calls = []

    async def send(**kwargs):
        calls.append(kwargs)

    await _send_command_result(send, CommandResult(text="No findings"))

    assert calls == [{"content": "No findings"}]


async def test_reply_command_result_batches_interaction_embeds():
    import discord

    from updater.presentation.discord_bot.bot import _reply_command_result
    from updater.presentation.discord_bot.commands import CommandResult

    response_calls = []
    followup_calls = []

    class FakeResponse:
        async def send_message(self, **kwargs):
            if len(kwargs.get("embeds", [])) > 10:
                raise ValueError("embeds has a maximum of 10 elements.")
            response_calls.append(kwargs)

    class FakeFollowup:
        async def send(self, **kwargs):
            if len(kwargs.get("embeds", [])) > 10:
                raise ValueError("embeds has a maximum of 10 elements.")
            followup_calls.append(kwargs)

    class FakeInteraction:
        response = FakeResponse()
        followup = FakeFollowup()

    embeds = [discord.Embed(title=f"Finding {index}") for index in range(11)]

    await _reply_command_result(FakeInteraction(), CommandResult(text="Target details", embeds=embeds))

    assert response_calls[0]["content"] == "Target details — showing 1-10 of 11"
    assert len(response_calls[0]["embeds"]) == 10
    assert followup_calls[0]["content"] == "Showing 11-11 of 11"
    assert len(followup_calls[0]["embeds"]) == 1


async def test_send_command_result_keeps_each_message_under_embed_total_limit():
    import discord

    from updater.presentation.discord_bot.bot import _send_command_result
    from updater.presentation.discord_bot.commands import CommandResult

    calls = []

    async def send(**kwargs):
        calls.append(kwargs)

    embeds = [discord.Embed(title=f"Finding {index}", description="x" * 3500) for index in range(3)]
    await _send_command_result(send, CommandResult(text="Search complete", embeds=embeds))

    assert len(calls) == 3
    assert all(len(call["embeds"]) == 1 for call in calls)
    for call in calls:
        total = sum(len(embed.title or "") + len(embed.description or "") for embed in call["embeds"])
        assert total <= 6000


async def test_run_notify_only_sends_vulnerabilities_created_since_sync_start():
    from unittest.mock import patch

    from updater.presentation.discord_bot.bot import _run_notify

    old = Vulnerability(
        id="old-vuln",
        advisory_id="CVE-2024-0001",
        severity="LOW",
        description="old bug already in db",
        created_at=datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc),
    )
    fresh = Vulnerability(
        id="fresh-vuln",
        advisory_id="CVE-2024-0002",
        severity="HIGH",
        description="new bug from this sync",
        created_at=datetime(2026, 5, 21, 13, 34, 30, tzinfo=timezone.utc),
    )
    target = Target(id="t1", name="Canon")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vuln_repo=FakeVulnRepo([old, fresh]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="old-vuln"),
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="fresh-vuln"),
        ]),
    )
    sent = []

    class FakeChannel:
        async def send(self, **kwargs):
            sent.append(kwargs)

    fake_now = datetime(2026, 5, 21, 14, 0, 0, tzinfo=timezone.utc)
    with patch("updater.presentation.discord_bot.bot.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        await _run_notify(
            services,
            FakeChannel(),
            timezone.utc,
            sync_started_at=datetime(2026, 5, 21, 13, 34, 0, tzinfo=timezone.utc),
        )

    assert sent[0]["content"] == (
        "Daily Vulnerability Report — 2026-05-21\n"
        "Targets processed: 1\n"
        "New findings: 1\n"
        "Errors: 0"
    )
    assert len(sent) == 2
    assert sent[1]["embed"].title == "CVE-2024-0002"


async def test_run_sync_returns_sync_start_timestamp():
    from unittest.mock import patch

    from updater.presentation.discord_bot.bot import _run_sync

    target = Target(id="t1", name="Canon")
    services = _services(target_repo=FakeTargetRepo([target]), sources=[])
    sync_start = datetime(2026, 5, 21, 13, 34, 30, tzinfo=timezone.utc)

    with patch("updater.presentation.discord_bot.bot.datetime") as mock_dt:
        mock_dt.now.return_value = sync_start
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await _run_sync(services)

    assert result is not None
    assert result.sync_started_at == sync_start
    assert result.sync_result.targets_processed == 1


async def test_run_sync_scans_versions_even_when_cve_sync_fails():
    from unittest.mock import patch

    from updater.application.version_scan import VersionScanReport
    from updater.presentation.discord_bot.bot import _run_sync

    services = _services(target_repo=FakeTargetRepo([Target(id="t1", name="Canon")]), sources=[])
    sentinel = VersionScanReport(changes=[], seeded=["Canon"], unchanged=[], errors=[])

    class BoomSync:
        def __init__(self, *args, **kwargs):
            pass

        def sync_all(self):
            raise RuntimeError("NVD unreachable")

    class OkScan:
        def __init__(self, *args, **kwargs):
            pass

        def scan_all(self):
            return sentinel

    with patch(
        "updater.presentation.discord_bot.bot.SyncVulnerabilitiesService", BoomSync
    ), patch("updater.presentation.discord_bot.bot.VersionScanService", OkScan):
        result = await _run_sync(services)

    assert result is not None
    assert result.sync_result is None
    assert result.version_report is sentinel


async def test_lookup_firmware_uses_stored_vendor_config():
    target = Target(id="t1", name="Canon MF654Cdw", vendor="Canon", vendor_alias="canon-mf654cdw")
    config = VendorConfig(
        vendor="Canon",
        url_template="https://example.com/{alias}/fw",
        attr_id="downloads",
        regex=r"version:([\d.]+).*href=[\"']([^\"']+)",
    )
    browser = FakeBrowserAdapter(html='version:2.1.0 <a href="https://example.com/fw.bin">download</a>')
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vendor_config_repo=FakeVendorConfigRepo([config]),
        browser=browser,
    )
    result = await handle_lookup_firmware(services, target_id=1)
    assert "Canon MF654Cdw" in result.text
    assert "2.1.0" in result.text
    assert "https://example.com/fw.bin" in result.text


async def test_lookup_firmware_returns_no_info_when_no_vendor():
    target = Target(id="t1", name="Some Target")
    services = _services(target_repo=FakeTargetRepo([target]))
    result = await handle_lookup_firmware(services, target_id=1)
    assert result.text == "Target 'Some Target' has no vendor. Set vendor before firmware lookup."
    assert result.ephemeral is True


async def test_lookup_firmware_returns_no_info_when_no_vendor_alias():
    target = Target(id="t1", name="Canon MF654Cdw", vendor="Canon")
    services = _services(target_repo=FakeTargetRepo([target]))
    result = await handle_lookup_firmware(services, target_id=1)
    assert result.text == (
        "Target 'Canon MF654Cdw' has no vendor_alias. Set vendor_alias before firmware lookup."
    )
    assert result.ephemeral is True


async def test_lookup_firmware_returns_no_info_when_no_config():
    target = Target(id="t1", name="Canon MF654Cdw", vendor="Canon", vendor_alias="canon-mf654cdw")
    services = _services(target_repo=FakeTargetRepo([target]))
    result = await handle_lookup_firmware(services, target_id=1)
    assert result.text == "No firmware vendor config found for Canon."
    assert result.ephemeral is True


async def test_lookup_firmware_returns_no_info_on_lookup_error():
    target = Target(id="t1", name="Canon MF654Cdw", vendor="Canon", vendor_alias="canon-mf654cdw")
    config = VendorConfig(
        vendor="Canon",
        url_template="https://example.com/{alias}/fw",
        attr_id="downloads",
        regex=r"version:([\d.]+).*href=[\"']([^\"']+)",
    )
    browser = FakeBrowserAdapter(html="<p>no match</p>")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vendor_config_repo=FakeVendorConfigRepo([config]),
        browser=browser,
    )
    result = await handle_lookup_firmware(services, target_id=1)
    assert result.text == (
        "Regex did not match #downloads at https://example.com/canon-mf654cdw/fw."
    )
    assert result.ephemeral is True


async def test_lookup_firmware_surfaces_error_when_http_adapter_not_configured():
    target = Target(id="t1", name="Chroma")
    config = VendorConfig(
        vendor="Chroma",
        target="Chroma",
        url_template="https://github.com/chroma-core/chroma/releases",
        regex=r"releases/tag/(\d+\.\d+\.\d+)",
        fetch="http",
    )
    services = Services(
        target_repo=FakeTargetRepo([target]),
        version_repo=FakeVersionRepo(),
        vulnerability_repo=FakeVulnRepo(),
        target_vulnerability_repo=FakeLinkRepo(),
        sources=[],
        vendor_config_repo=FakeVendorConfigRepo([config]),
        browser=FakeBrowserAdapter(),
        http=None,
    )
    result = await handle_lookup_firmware(services, target_id=1)
    assert result.text == "HTTP fetch adapter is not configured for this lookup."
    assert result.ephemeral is True


async def test_lookup_firmware_with_runtime_inputs():
    target = Target(id="t1", name="Canon MF654Cdw", vendor="Canon", vendor_alias="canon-mf654cdw")
    browser = FakeBrowserAdapter(html='version:3.0.0 <a href="https://example.com/fw3.bin">download</a>')
    services = _services(
        target_repo=FakeTargetRepo([target]),
        browser=browser,
    )
    result = await handle_lookup_firmware(
        services,
        target_id=1,
        url_template="https://example.com/{alias}/fw",
        attr_id="downloads",
        regex=r"version:([\d.]+).*href=[\"']([^\"']+)",
    )
    assert "3.0.0" in result.text
    assert "fw3.bin" in result.text


async def test_set_vendor_alias_updates_target():
    target = Target(id="t1", name="Canon MF654Cdw", vendor="Canon")
    services = _services(target_repo=FakeTargetRepo([target]))
    result = await handle_set_vendor_alias(services, target_id=1, vendor_alias="canon-mf654cdw")
    assert "canon-mf654cdw" in result.text
    updated = services.target_repo.find_by_name("Canon MF654Cdw")
    assert updated.vendor_alias == "canon-mf654cdw"


async def test_set_vendor_alias_rejects_invalid_target_id():
    services = _services()
    result = await handle_set_vendor_alias(services, target_id=1, vendor_alias="test")
    assert "Invalid target ID" in result.text


async def test_import_vendor_firmware_imports_csv():
    csv_data = (
        "vendor,url_template,attr_id,regex\n"
        "Canon,https://example.com/{alias}/fw,downloads,(v[\\d.]+).*(https://[^\"']+)\n"
        "TP-Link,https://tplink.com/{alias}/fw,content,(v[\\d.]+).*(https://[^\"']+)\n"
    ).encode()
    services = _services()
    result = await handle_import_vendor_firmware(services, csv_bytes=csv_data)
    assert "2" in result.text
    assert services.vendor_config_repo.find_by_vendor("Canon") is not None
    assert services.vendor_config_repo.find_by_vendor("TP-Link") is not None


async def test_import_vendor_firmware_reports_invalid_rows():
    csv_data = (
        "vendor,url_template,attr_id,regex\n"
        "Canon,https://example.com/{alias}/fw,downloads,(v[\\d.]+).*(https://[^\"']+)\n"
        "BadVendor,http://no-alias.com/fw,downloads,(bad\n"
    ).encode()
    services = _services()
    result = await handle_import_vendor_firmware(services, csv_bytes=csv_data)
    assert "1" in result.text
    assert services.vendor_config_repo.find_by_vendor("Canon") is not None
    assert "BadVendor" in result.text


async def test_set_vendor_firmware_creates_config():
    services = _services()
    result = await handle_set_vendor_firmware(
        services,
        vendor="Canon",
        url_template="https://example.com/{alias}/firmware",
        attr_id="downloads",
        regex=r"(v[\d.]+).*(https://[^\"']+)",
    )
    assert "Canon" in result.text
    saved = services.vendor_config_repo.find_by_vendor("Canon")
    assert saved is not None
    assert saved.url_template == "https://example.com/{alias}/firmware"


async def test_set_vendor_firmware_rejects_invalid_regex():
    services = _services()
    result = await handle_set_vendor_firmware(
        services,
        vendor="Canon",
        url_template="https://example.com/{alias}/firmware",
        attr_id="downloads",
        regex="[invalid(",
    )
    assert "invalid" in result.text.lower()


async def test_set_vendor_firmware_allows_missing_alias_placeholder():
    services = _services()
    result = await handle_set_vendor_firmware(
        services,
        vendor="Canon",
        url_template="https://example.com/firmware",
        attr_id="downloads",
        regex=r"(v[\d.]+).*(https://[^\"']+)",
    )
    assert "saved" in result.text.lower()


async def test_import_vendor_firmware_supports_version_checker_columns():
    csv_data = (
        "target,vendor,url_template,fetch,selector,select,regex\n"
        "Chroma,Chroma,https://github.com/chroma-core/chroma/releases,http,,first,"
        'releases/tag/(\\d+\\.\\d+\\.\\d+)\n'
    ).encode()
    services = _services()
    result = await handle_import_vendor_firmware(services, csv_bytes=csv_data)
    assert "1" in result.text
    saved = services.vendor_config_repo.find_by_vendor("Chroma")
    assert saved is not None
    assert saved.target == "Chroma"
    assert saved.fetch == "http"
    assert saved.attr_id == ""


async def test_set_vendor_firmware_allows_fixed_url_and_target_binding():
    services = _services()
    result = await handle_set_vendor_firmware(
        services,
        vendor="Chroma",
        url_template="https://github.com/chroma-core/chroma/releases",
        attr_id="",
        regex=r"releases/tag/(\d+\.\d+\.\d+)",
        target="Chroma",
        fetch="http",
    )
    assert "Chroma" in result.text
    saved = services.vendor_config_repo.find_by_vendor("Chroma")
    assert saved.target == "Chroma"
    assert saved.fetch == "http"


async def test_check_version_uses_target_bound_http_config():
    from updater.domain.models import Target, VendorConfig
    target = Target(id="t1", name="Chroma")
    config = VendorConfig(
        vendor="Chroma", target="Chroma",
        url_template="https://github.com/chroma-core/chroma/releases",
        regex=r'releases/tag/(\d+\.\d+\.\d+)(?=["/#?])', fetch="http",
    )
    http = FakeHttpAdapter(html='<a href="/chroma-core/chroma/releases/tag/1.5.9">x</a>')
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vendor_config_repo=FakeVendorConfigRepo([config]),
        http=http,
    )
    result = await handle_lookup_firmware(services, target_id=1)
    assert "1.5.9" in result.text
    assert "Download" not in result.text


def test_scan_versions_reports_no_updates_on_first_scan():
    import asyncio
    from updater.domain.models import Target, VendorConfig

    target = Target(name="Chroma", id="c1")
    config = VendorConfig(vendor="Chroma", target="Chroma",
                          url_template="https://x/releases", fetch="http",
                          regex=r"v(\d+\.\d+\.\d+)", select="first")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vendor_config_repo=FakeVendorConfigRepo([config]),
        version_repo=FakeVersionRepo(),
        http=FakeHttpAdapter(html="release v1.6.0"),
    )
    result = asyncio.run(handle_scan_versions(services))
    assert "No version updates." in result.text
    assert "scanned 1" in result.text


def test_scan_versions_reports_a_change():
    import asyncio
    from updater.domain.models import Target, TargetVersion, VendorConfig

    target = Target(name="Chroma", id="c1")
    config = VendorConfig(vendor="Chroma", target="Chroma",
                          url_template="https://x/releases", fetch="http",
                          regex=r"v(\d+\.\d+\.\d+)", select="first")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vendor_config_repo=FakeVendorConfigRepo([config]),
        version_repo=FakeVersionRepo(latest={"c1": TargetVersion(target_id="c1", version="1.5.9")}),
        http=FakeHttpAdapter(html="release v1.6.0"),
    )
    result = asyncio.run(handle_scan_versions(services))
    assert "• Chroma: 1.5.9 → 1.6.0" in result.text


def test_scan_versions_footer_lists_failing_targets():
    import asyncio
    from updater.domain.models import Target, VendorConfig
    target = Target(name="Chroma", id="c1")
    config = VendorConfig(vendor="Chroma", target="Chroma",
                          url_template="https://x/releases", fetch="http",
                          regex=r"nomatch(\d+\.\d+\.\d+)", select="first")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vendor_config_repo=FakeVendorConfigRepo([config]),
        version_repo=FakeVersionRepo(),
        http=FakeHttpAdapter(html="release v1.6.0"),
    )
    result = asyncio.run(handle_scan_versions(services))
    assert "1 error(s)" in result.text
    assert "Chroma" in result.text
