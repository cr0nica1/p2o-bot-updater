from updater.application.import_targets import ImportTargetsService
from updater.domain.models import Target, TargetVersion


class FakeTargetRepository:
    def __init__(self):
        self.targets = {}

    def upsert(self, target: Target) -> Target:
        target.id = target.id or f"target-{len(self.targets) + 1}"
        self.targets[target.normalized_name] = target
        return target

    def list_all(self):
        return list(self.targets.values())

    def find_by_name(self, name: str):
        return self.targets.get(name.strip().lower())


class FakeTargetVersionRepository:
    def __init__(self):
        self.versions = []

    def upsert(self, version: TargetVersion) -> TargetVersion:
        version.id = version.id or f"version-{len(self.versions) + 1}"
        self.versions.append(version)
        return version


def test_import_targets_upserts_target_and_version():
    target_repo = FakeTargetRepository()
    version_repo = FakeTargetVersionRepository()
    service = ImportTargetsService(target_repo, version_repo)

    result = service.import_items([
        (Target(name="Adobe Acrobat Reader"), TargetVersion(version="2024.005.20320", version_type="software"))
    ])

    assert result.targets_imported == 1
    assert result.versions_imported == 1
    assert target_repo.list_all()[0].id == "target-1"
    assert version_repo.versions[0].target_id == "target-1"


def test_import_targets_allows_no_version():
    target_repo = FakeTargetRepository()
    version_repo = FakeTargetVersionRepository()
    service = ImportTargetsService(target_repo, version_repo)

    result = service.import_items([(Target(name="VMware Workstation"), None)])

    assert result.targets_imported == 1
    assert result.versions_imported == 0
    assert version_repo.versions == []
