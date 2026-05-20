from updater.domain.models import Target, TargetVulnerability, Vulnerability
from updater.presentation.discord_bot.commands import (
    CommandResult,
    Services,
    handle_add_target,
    handle_add_vuln,
    handle_import_targets,
    handle_list_targets,
    handle_remove_target,
    handle_set_schedule,
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


class FakeVersionRepo:
    def __init__(self):
        self.calls = []

    def upsert(self, version):
        self.calls.append(version)
        return version


class FakeVulnRepo:
    def __init__(self, items=None):
        self.items = {v.advisory_id: v for v in (items or [])}

    def upsert(self, vuln):
        vuln.id = vuln.id or vuln.advisory_id
        self.items[vuln.advisory_id] = vuln
        return vuln

    def list_all(self):
        return list(self.items.values())


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


def _services(target_repo=None, vuln_repo=None, link_repo=None, version_repo=None, sources=None):
    return Services(
        target_repo=target_repo or FakeTargetRepo(),
        version_repo=version_repo or FakeVersionRepo(),
        vulnerability_repo=vuln_repo or FakeVulnRepo(),
        target_vulnerability_repo=link_repo or FakeLinkRepo(),
        sources=sources or [],
    )


async def test_list_targets_empty():
    result = await handle_list_targets(_services())
    assert isinstance(result, CommandResult)
    assert "No targets" in result.text


async def test_list_targets_returns_names():
    services = _services(target_repo=FakeTargetRepo([
        Target(id="t1", name="Adobe Reader"),
        Target(id="t2", name="Canon MF654Cdw"),
    ]))
    result = await handle_list_targets(services)
    assert "Adobe Reader" in result.text
    assert "Canon MF654Cdw" in result.text


async def test_show_target_includes_vulnerability_count():
    target = Target(id="t1", name="Adobe Reader")
    link = TargetVulnerability(target_id="t1", vulnerability_id="v1")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        link_repo=FakeLinkRepo([link]),
    )
    result = await handle_show_target(services, name="Adobe Reader")
    assert "Adobe Reader" in result.text
    assert "1" in result.text


async def test_show_target_not_found():
    result = await handle_show_target(_services(), name="Nope")
    assert "not found" in result.text.lower()


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


async def test_remove_target_removes_target_and_links():
    target = Target(id="t1", name="Adobe Reader")
    link = TargetVulnerability(target_id="t1", vulnerability_id="v1")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        link_repo=FakeLinkRepo([link]),
    )
    result = await handle_remove_target(services, names=["Adobe Reader"])
    assert "Removed" in result.text
    assert services.target_repo.list_all() == []
    assert services.target_vulnerability_repo.list_all() == []


async def test_remove_target_reports_missing():
    services = _services()
    result = await handle_remove_target(services, names=["Adobe Reader"])
    assert "not found" in result.text.lower()


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
