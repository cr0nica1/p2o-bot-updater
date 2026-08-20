from __future__ import annotations

import re
from dataclasses import dataclass

_KEEP = re.compile(r"chromadb|chroma-core|chroma db", re.I)
_CHROMA_NAME = "chroma"


@dataclass
class PurgeChromaResult:
    unlinked: int = 0
    deleted_vulnerabilities: int = 0


class PurgeChromaService:
    def __init__(self, target_repo, vulnerability_repo, link_repo) -> None:
        self.target_repo = target_repo
        self.vulnerability_repo = vulnerability_repo
        self.link_repo = link_repo

    def run(self) -> PurgeChromaResult:
        target = self.target_repo.find_by_name("Chroma")
        if target is None:
            return PurgeChromaResult()
        target_id = target.storage_id
        vulns = {v.id: v for v in self.vulnerability_repo.list_all() if v.id}
        for v in list(vulns.values()):
            vulns[v.advisory_id] = v
        result = PurgeChromaResult()
        chroma_junk_ids: set[str] = set()
        for link in self.link_repo.list_all():
            if link.target_id != target_id and (link.target_name or "").casefold() != _CHROMA_NAME:
                continue
            vuln = vulns.get(link.vulnerability_id)
            if vuln is None:
                continue
            blob = f"{vuln.advisory_id} {vuln.description or ''}"
            if _KEEP.search(blob):
                continue
            result.unlinked += self.link_repo.delete_link(target_id, link.vulnerability_id)
            chroma_junk_ids.add(link.vulnerability_id)

        remaining = {link.vulnerability_id for link in self.link_repo.list_all()}
        for vid in chroma_junk_ids:
            if vid not in remaining:
                if self.vulnerability_repo.delete(vid):
                    result.deleted_vulnerabilities += 1
        return result
