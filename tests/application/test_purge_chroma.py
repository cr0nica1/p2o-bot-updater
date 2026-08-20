from updater.application.purge_chroma import PurgeChromaService
from updater.domain.models import Target, TargetVulnerability, Vulnerability


class FakeTargets:
    def __init__(self, targets):
        self.targets = targets
    def find_by_name(self, name):
        return next((t for t in self.targets if t.name.lower() == name.lower()), None)
    def list_all(self):
        return list(self.targets)


class FakeVulns:
    def __init__(self, items):
        self.items = {v.id: v for v in items}
    def list_all(self):
        return list(self.items.values())
    def delete(self, vid):
        for key, v in list(self.items.items()):
            if v.id == vid or v.advisory_id == vid:
                del self.items[key]
                return True
        return False


class FakeLinks:
    def __init__(self, links):
        self.links = list(links)
    def list_all(self):
        return list(self.links)
    def delete_link(self, target_id, vulnerability_id):
        before = len(self.links)
        self.links = [
            link for link in self.links
            if not (link.target_id == target_id and link.vulnerability_id == vulnerability_id)
        ]
        return before - len(self.links)


def test_purge_unlinks_ffmpeg_chroma_keeps_chromadb():
    chroma = Target(id="c1", name="Chroma")
    keep = Vulnerability(id="k1", advisory_id="CVE-2026-8828", description="ChromaDB Rust project")
    junk = Vulnerability(id="j1", advisory_id="CVE-2012-0851", description="libavcodec chroma format")
    links = FakeLinks([
        TargetVulnerability(target_id="c1", target_name="Chroma", vulnerability_id="k1"),
        TargetVulnerability(target_id="c1", target_name="Chroma", vulnerability_id="j1"),
    ])
    vulns = FakeVulns([keep, junk])
    result = PurgeChromaService(FakeTargets([chroma]), vulns, links).run()
    assert result.unlinked == 1
    assert result.deleted_vulnerabilities == 1
    assert [l.vulnerability_id for l in links.links] == ["k1"]
    assert "j1" not in vulns.items
    assert "k1" in vulns.items


def test_purge_does_not_delete_vuln_still_linked_elsewhere():
    chroma = Target(id="c1", name="Chroma")
    shared = Vulnerability(id="s1", advisory_id="CVE-2012-0851", description="chroma format")
    links = FakeLinks([
        TargetVulnerability(target_id="c1", target_name="Chroma", vulnerability_id="s1"),
        TargetVulnerability(target_id="other", target_name="Other", vulnerability_id="s1"),
    ])
    vulns = FakeVulns([shared])
    PurgeChromaService(FakeTargets([chroma]), vulns, links).run()
    remaining = {(l.target_id, l.vulnerability_id) for l in links.links}
    assert remaining == {("other", "s1")}
    assert "s1" in vulns.items
