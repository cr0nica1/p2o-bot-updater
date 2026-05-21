from updater.application.sync_vulnerabilities import SyncVulnerabilitiesService
from updater.domain.models import Target, TargetVulnerability, Vulnerability


class FakeTargetRepository:
    def __init__(self, targets):
        self.targets = targets

    def list_all(self):
        return self.targets

    def find_by_name(self, name: str):
        return next((target for target in self.targets if target.name == name), None)

    def upsert(self, target):
        return target


class FakeVulnerabilityRepository:
    def __init__(self, items=None):
        self.items = {item.advisory_id: item for item in items or []}

    def upsert(self, vulnerability: Vulnerability) -> Vulnerability:
        vulnerability.id = vulnerability.id or vulnerability.advisory_id
        self.items[vulnerability.advisory_id] = vulnerability
        return vulnerability

    def list_all(self):
        return list(self.items.values())


class FakeTargetVulnerabilityRepository:
    def __init__(self, links=None):
        self.links = list(links or [])

    def upsert(self, link: TargetVulnerability) -> TargetVulnerability:
        link.id = link.id or f"link-{len(self.links) + 1}"
        self.links.append(link)
        return link

    def list_all(self):
        return self.links


class FakeSource:
    source_name = "fake"

    def __init__(self, source_name="fake"):
        self.source_name = source_name
        self.calls = []

    def search(self, target: Target, query: str, since_year=None):
        self.calls.append({"target": target, "query": query, "since_year": since_year})
        if query == "Adobe Reader":
            return [(
                Vulnerability(advisory_id="CVE-2025-1234", sources=["fake"], description="Example"),
                {"matched": query},
            )]
        return []


def test_sync_searches_name_and_aliases_and_links_evidence():
    target = Target(id="target-1", name="Adobe Acrobat Reader", aliases=["Adobe Reader"])
    vuln_repo = FakeVulnerabilityRepository()
    link_repo = FakeTargetVulnerabilityRepository()
    service = SyncVulnerabilitiesService(
        target_repo=FakeTargetRepository([target]),
        vulnerability_repo=vuln_repo,
        target_vulnerability_repo=link_repo,
        sources=[FakeSource()],
    )

    result = service.sync_all()

    assert result.targets_processed == 1
    assert result.vulnerabilities_seen == 1
    assert vuln_repo.list_all()[0].advisory_id == "CVE-2025-1234"
    assert link_repo.links[0].target_id == "target-1"
    assert link_repo.links[0].target_name == "Adobe Acrobat Reader"
    assert link_repo.links[0].matched_queries == ["Adobe Reader"]


def test_sync_reports_progress_events():
    events = []
    target = Target(id="target-1", name="Adobe Acrobat Reader", aliases=["Adobe Reader"])
    vuln_repo = FakeVulnerabilityRepository()
    link_repo = FakeTargetVulnerabilityRepository()
    service = SyncVulnerabilitiesService(
        target_repo=FakeTargetRepository([target]),
        vulnerability_repo=vuln_repo,
        target_vulnerability_repo=link_repo,
        sources=[FakeSource()],
        progress=events.append,
    )

    service.sync_all()

    assert events == [
        "sync:start total_targets=1",
        "sync:target target=Adobe Acrobat Reader (1/1)",
        "sync:query source=fake query=Adobe Acrobat Reader hits=0",
        "sync:query source=fake query=Adobe Reader hits=1",
        "sync:target_done target=Adobe Acrobat Reader vulnerabilities=1 links=1 errors=0",
        "sync:done targets_processed=1 vulnerabilities_seen=1 links_updated=1 errors=0",
    ]


def test_sync_passes_latest_zdi_year_to_zdi_source():
    target = Target(id="target-1", name="HP DeskJet 2855e")
    vulnerability = Vulnerability(
        id="vuln-1",
        advisory_id="CVE-2026-4682",
        aliases=["ZDI-26-280"],
        sources=["zdi"],
        raw={"zdi": {"zdi_id": "ZDI-26-280"}},
    )
    link = TargetVulnerability(
        target_id="target-1",
        target_name="HP DeskJet 2855e",
        vulnerability_id="vuln-1",
    )
    zdi_source = FakeSource("zdi")

    service = SyncVulnerabilitiesService(
        target_repo=FakeTargetRepository([target]),
        vulnerability_repo=FakeVulnerabilityRepository([vulnerability]),
        target_vulnerability_repo=FakeTargetVulnerabilityRepository([link]),
        sources=[zdi_source],
    )

    service.sync_all()

    assert zdi_source.calls[0]["since_year"] == 2026


def test_sync_passes_latest_cve_year_to_nvd_source():
    target = Target(id="target-1", name="MikroTik RB4011iGS+RM")
    vulnerability = Vulnerability(
        id="vuln-1",
        advisory_id="CVE-2026-1234",
        sources=["nvd"],
    )
    link = TargetVulnerability(
        target_id="target-1",
        target_name="MikroTik RB4011iGS+RM",
        vulnerability_id="vuln-1",
    )
    nvd_source = FakeSource("nvd")

    service = SyncVulnerabilitiesService(
        target_repo=FakeTargetRepository([target]),
        vulnerability_repo=FakeVulnerabilityRepository([vulnerability]),
        target_vulnerability_repo=FakeTargetVulnerabilityRepository([link]),
        sources=[nvd_source],
    )

    service.sync_all()

    assert nvd_source.calls[0]["since_year"] == 2026


def test_sync_passes_no_since_year_without_stored_history():
    target = Target(id="target-1", name="MikroTik RB4011iGS+RM")
    nvd_source = FakeSource("nvd")
    zdi_source = FakeSource("zdi")

    service = SyncVulnerabilitiesService(
        target_repo=FakeTargetRepository([target]),
        vulnerability_repo=FakeVulnerabilityRepository(),
        target_vulnerability_repo=FakeTargetVulnerabilityRepository(),
        sources=[nvd_source, zdi_source],
    )

    service.sync_all()

    assert nvd_source.calls[0]["since_year"] is None
    assert zdi_source.calls[0]["since_year"] is None


def test_sync_ignores_other_targets_history_when_computing_since_year():
    target_a = Target(id="target-a", name="Target A")
    target_b = Target(id="target-b", name="Target B")
    vulnerability = Vulnerability(
        id="vuln-1",
        advisory_id="CVE-2026-1234",
        sources=["nvd"],
    )
    link = TargetVulnerability(
        target_id="target-a",
        target_name="Target A",
        vulnerability_id="vuln-1",
    )
    nvd_source = FakeSource("nvd")

    service = SyncVulnerabilitiesService(
        target_repo=FakeTargetRepository([target_a, target_b]),
        vulnerability_repo=FakeVulnerabilityRepository([vulnerability]),
        target_vulnerability_repo=FakeTargetVulnerabilityRepository([link]),
        sources=[nvd_source],
    )

    service.sync_one("Target B")

    assert nvd_source.calls[0]["target"] == target_b
    assert nvd_source.calls[0]["since_year"] is None


def test_sync_one_searches_full_history_even_with_existing_target_history():
    target = Target(id="target-1", name="Target B")
    vulnerability = Vulnerability(
        id="vuln-1",
        advisory_id="CVE-2026-1234",
        sources=["nvd"],
    )
    link = TargetVulnerability(
        target_id="target-1",
        target_name="Target B",
        vulnerability_id="vuln-1",
    )
    nvd_source = FakeSource("nvd")

    service = SyncVulnerabilitiesService(
        target_repo=FakeTargetRepository([target]),
        vulnerability_repo=FakeVulnerabilityRepository([vulnerability]),
        target_vulnerability_repo=FakeTargetVulnerabilityRepository([link]),
        sources=[nvd_source],
    )

    service.sync_one("Target B")

    assert nvd_source.calls[0]["target"] == target
    assert nvd_source.calls[0]["since_year"] is None
