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
    def __init__(self):
        self.items = {}

    def upsert(self, vulnerability: Vulnerability) -> Vulnerability:
        vulnerability.id = vulnerability.id or vulnerability.advisory_id
        self.items[vulnerability.advisory_id] = vulnerability
        return vulnerability

    def list_all(self):
        return list(self.items.values())


class FakeTargetVulnerabilityRepository:
    def __init__(self):
        self.links = []

    def upsert(self, link: TargetVulnerability) -> TargetVulnerability:
        link.id = link.id or f"link-{len(self.links) + 1}"
        self.links.append(link)
        return link

    def list_all(self):
        return self.links


class FakeSource:
    source_name = "fake"

    def search(self, target: Target, query: str):
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
    assert link_repo.links[0].matched_queries == ["Adobe Reader"]
