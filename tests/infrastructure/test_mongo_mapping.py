from updater.domain.models import Target, TargetVulnerability, Vulnerability
from updater.infrastructure.mongo import (
    MongoTargetRepository,
    MongoTargetVersionRepository,
    MongoTargetVulnerabilityRepository,
    MongoVulnerabilityRepository,
    target_to_document,
    target_vulnerability_to_document,
    vulnerability_to_document,
)


def test_target_document_contains_normalized_name_and_raw_metadata():
    target = Target(name=" Adobe Reader ", aliases=["Acrobat"], raw_metadata={"notes": "contest"})

    document = target_to_document(target)

    assert document["name"] == " Adobe Reader "
    assert document["normalized_name"] == "adobe reader"
    assert document["aliases"] == ["Acrobat"]
    assert document["raw_metadata"] == {"notes": "contest"}


def test_vulnerability_document_uses_advisory_id_as_unique_key():
    vulnerability = Vulnerability(advisory_id="CVE-2025-1234", sources=["nvd"], aliases=["ZDI-CAN-12345"])

    document = vulnerability_to_document(vulnerability)

    assert document["advisory_id"] == "CVE-2025-1234"
    assert document["aliases"] == ["ZDI-CAN-12345"]
    assert document["sources"] == ["nvd"]


def test_target_vulnerability_document_contains_target_name():
    link = TargetVulnerability(target_id="target-1", target_name="Adobe Reader", vulnerability_id="vuln-1")

    document = target_vulnerability_to_document(link)

    assert document["target_name"] == "Adobe Reader"


def test_repository_distinguishes_database_from_collection():
    """PyMongo Database.__getattr__ returns a Collection for any attribute,
    so hasattr(db, 'find_one_and_update') is True. _as_collection must
    not mistake a Database for a Collection."""

    class FakeCollection:
        def find_one_and_update(self, *args, **kwargs):
            return {"_id": "test"}

    class FakeDatabase:
        """Simulates PyMongo Database: any attribute access returns a Collection."""
        def __getattr__(self, name):
            return FakeCollection()

    db = FakeDatabase()
    repo = MongoTargetRepository(db)

    assert isinstance(repo.collection, FakeCollection)
    assert repo.collection is not db


class FakeDeleteCollection:
    def __init__(self):
        self.deleted = False

    def delete_many(self, filter_doc):
        self.deleted = True
        return type("Result", (), {"deleted_count": 5})()


class FakeDeleteDatabase:
    def __getattr__(self, name):
        return FakeDeleteCollection()


def test_target_repository_delete_all_calls_delete_many():
    db = FakeDeleteDatabase()
    repo = MongoTargetRepository(db)
    repo.delete_all()

    assert repo.collection.deleted is True


def test_vulnerability_repository_delete_all_calls_delete_many():
    db = FakeDeleteDatabase()
    repo = MongoVulnerabilityRepository(db)
    repo.delete_all()

    assert repo.collection.deleted is True


def test_target_version_repository_delete_all_calls_delete_many():
    db = FakeDeleteDatabase()
    repo = MongoTargetVersionRepository(db)
    repo.delete_all()

    assert repo.collection.deleted is True


def test_target_vulnerability_repository_delete_all_calls_delete_many():
    db = FakeDeleteDatabase()
    repo = MongoTargetVulnerabilityRepository(db)
    repo.delete_all()

    assert repo.collection.deleted is True


class FakeVulnerabilityUpsertCollection:
    def __init__(self):
        self.document = None

    def find_one(self, filter_doc):
        if self.document and self.document["advisory_id"] == filter_doc["advisory_id"]:
            return dict(self.document)
        return None

    def find_one_and_update(self, filter_doc, update_doc, **kwargs):
        if self.document is None:
            document = dict(update_doc["$setOnInsert"], **update_doc["$set"])
            document["_id"] = "vuln-1"
            self.document = document
        else:
            for key, value in update_doc["$set"].items():
                self.document[key] = value
        return self.document


class FakeVulnerabilityUpsertDatabase:
    def __init__(self):
        self.vulnerabilities = FakeVulnerabilityUpsertCollection()


def test_vulnerability_repository_merges_duplicate_advisory_sources():
    from updater.infrastructure.mongo import merge_vulnerability_documents

    existing = {
        "_id": "vuln-1",
        "advisory_id": "CVE-2024-12647",
        "aliases": [],
        "sources": ["nvd"],
        "description": "Short NVD description",
        "references": ["https://nvd.example/ref"],
        "raw": {"nvd": {"cve": {"id": "CVE-2024-12647"}}},
    }
    incoming = {
        "advisory_id": "CVE-2024-12647",
        "aliases": ["ZDI-24-001"],
        "sources": ["zdi"],
        "description": "Longer ZDI vulnerability details description",
        "references": ["https://zdi.example/advisory"],
        "raw": {"zdi": {"zdi_id": "ZDI-24-001"}},
    }

    merged = merge_vulnerability_documents(existing, incoming)

    assert merged["sources"] == ["nvd", "zdi"]
    assert merged["aliases"] == ["ZDI-24-001"]
    assert merged["references"] == ["https://nvd.example/ref", "https://zdi.example/advisory"]
    assert merged["raw"] == {
        "nvd": {"cve": {"id": "CVE-2024-12647"}},
        "zdi": {"zdi_id": "ZDI-24-001"},
    }
    assert merged["description"] == "Longer ZDI vulnerability details description"


def test_vulnerability_merge_prefers_zdi_description_over_longer_nvd_description():
    from updater.infrastructure.mongo import merge_vulnerability_documents

    existing = {
        "_id": "vuln-1",
        "advisory_id": "CVE-2024-12647",
        "aliases": [],
        "sources": ["nvd"],
        "description": "Long NVD description that should not win over the ZDI vulnerability detail row",
        "references": [],
        "raw": {"nvd": {"cve": {"id": "CVE-2024-12647"}}},
    }
    incoming = {
        "advisory_id": "CVE-2024-12647",
        "aliases": ["ZDI-24-001"],
        "sources": ["zdi"],
        "description": "ZDI vulnerability detail",
        "references": [],
        "raw": {"zdi": {"zdi_id": "ZDI-24-001"}},
    }

    merged = merge_vulnerability_documents(existing, incoming)

    assert merged["description"] == "ZDI vulnerability detail"


def test_vulnerability_merge_keeps_existing_zdi_description_over_incoming_nvd_description():
    from updater.infrastructure.mongo import merge_vulnerability_documents

    existing = {
        "_id": "vuln-1",
        "advisory_id": "CVE-2024-12647",
        "aliases": ["ZDI-24-001"],
        "sources": ["zdi"],
        "description": "ZDI vulnerability detail",
        "references": [],
        "raw": {"zdi": {"zdi_id": "ZDI-24-001"}},
    }
    incoming = {
        "advisory_id": "CVE-2024-12647",
        "aliases": [],
        "sources": ["nvd"],
        "description": "Long NVD description that should not replace the ZDI vulnerability detail row",
        "references": [],
        "raw": {"nvd": {"cve": {"id": "CVE-2024-12647"}}},
    }

    merged = merge_vulnerability_documents(existing, incoming)

    assert merged["description"] == "ZDI vulnerability detail"


def test_target_repository_delete_returns_true_when_match_found():
    class FakeCollection:
        def __init__(self):
            self.last_filter = None

        def delete_one(self, filter):
            self.last_filter = filter
            class Result:
                deleted_count = 1
            return Result()

    collection = FakeCollection()
    repo = MongoTargetRepository.__new__(MongoTargetRepository)
    repo.collection = collection

    deleted = repo.delete(" Adobe Reader ")

    assert deleted is True
    assert collection.last_filter == {"normalized_name": "adobe reader"}


def test_target_repository_delete_returns_false_when_no_match():
    class FakeCollection:
        def delete_one(self, filter):
            class Result:
                deleted_count = 0
            return Result()

    repo = MongoTargetRepository.__new__(MongoTargetRepository)
    repo.collection = FakeCollection()

    assert repo.delete("Nothing") is False


def test_target_vulnerability_repository_delete_by_target_returns_count():
    class FakeCollection:
        def __init__(self):
            self.last_filter = None

        def delete_many(self, filter):
            self.last_filter = filter
            class Result:
                deleted_count = 3
            return Result()

    collection = FakeCollection()
    repo = MongoTargetVulnerabilityRepository.__new__(MongoTargetVulnerabilityRepository)
    repo.collection = collection

    deleted = repo.delete_by_target("target-1")

    assert deleted == 3
    assert collection.last_filter == {"target_id": "target-1"}
