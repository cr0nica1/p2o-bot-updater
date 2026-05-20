from __future__ import annotations

from typing import Any

try:
    from pymongo import ASCENDING, MongoClient, ReturnDocument
except ModuleNotFoundError:  # pragma: no cover - exercised only when dependency is absent
    ASCENDING = 1
    MongoClient = None
    ReturnDocument = None

from updater.domain.models import (
    Target,
    TargetVersion,
    TargetVulnerability,
    Vulnerability,
    normalize_name,
)


def _document_id(document: dict[str, Any]) -> str | None:
    value = document.get("_id")
    return str(value) if value is not None else None


def target_to_document(target: Target) -> dict[str, Any]:
    return {
        "name": target.name,
        "normalized_name": target.normalized_name,
        "aliases": list(target.aliases),
        "vendor": target.vendor,
        "category": target.category,
        "raw_metadata": dict(target.raw_metadata),
        "created_at": target.created_at,
        "updated_at": target.updated_at,
    }


def target_from_document(document: dict[str, Any]) -> Target:
    return Target(
        id=_document_id(document),
        name=document["name"],
        aliases=list(document.get("aliases", [])),
        vendor=document.get("vendor"),
        category=document.get("category"),
        raw_metadata=dict(document.get("raw_metadata", {})),
        created_at=document["created_at"],
        updated_at=document["updated_at"],
    )


def target_version_to_document(version: TargetVersion) -> dict[str, Any]:
    return {
        "target_id": version.target_id,
        "version": version.version,
        "version_type": version.version_type,
        "release_date": version.release_date,
        "source_url": version.source_url,
        "is_latest": version.is_latest,
        "raw": dict(version.raw),
        "first_seen_at": version.first_seen_at,
        "last_seen_at": version.last_seen_at,
    }


def target_version_from_document(document: dict[str, Any]) -> TargetVersion:
    return TargetVersion(
        id=_document_id(document),
        target_id=document.get("target_id"),
        version=document.get("version"),
        version_type=document.get("version_type"),
        release_date=document.get("release_date"),
        source_url=document.get("source_url"),
        is_latest=document.get("is_latest"),
        raw=dict(document.get("raw", {})),
        first_seen_at=document["first_seen_at"],
        last_seen_at=document["last_seen_at"],
    )


def vulnerability_to_document(vulnerability: Vulnerability) -> dict[str, Any]:
    return {
        "advisory_id": vulnerability.advisory_id,
        "aliases": list(vulnerability.aliases),
        "sources": list(vulnerability.sources),
        "cvss_score": vulnerability.cvss_score,
        "severity": vulnerability.severity,
        "description": vulnerability.description,
        "references": list(vulnerability.references),
        "published_date": vulnerability.published_date,
        "raw": dict(vulnerability.raw),
        "created_at": vulnerability.created_at,
        "updated_at": vulnerability.updated_at,
    }


def vulnerability_from_document(document: dict[str, Any]) -> Vulnerability:
    return Vulnerability(
        id=_document_id(document),
        advisory_id=document["advisory_id"],
        aliases=list(document.get("aliases", [])),
        sources=list(document.get("sources", [])),
        cvss_score=document.get("cvss_score"),
        severity=document.get("severity"),
        description=document.get("description"),
        references=list(document.get("references", [])),
        published_date=document.get("published_date"),
        raw=dict(document.get("raw", {})),
        created_at=document["created_at"],
        updated_at=document["updated_at"],
    )


def target_vulnerability_to_document(link: TargetVulnerability) -> dict[str, Any]:
    return {
        "target_id": link.target_id,
        "vulnerability_id": link.vulnerability_id,
        "target_name": link.target_name,
        "affected_versions": list(link.affected_versions),
        "fixed_versions": list(link.fixed_versions),
        "matched_queries": list(link.matched_queries),
        "evidence_sources": list(link.evidence_sources),
        "first_seen_at": link.first_seen_at,
        "last_seen_at": link.last_seen_at,
    }


def target_vulnerability_from_document(document: dict[str, Any]) -> TargetVulnerability:
    return TargetVulnerability(
        id=_document_id(document),
        target_id=document["target_id"],
        vulnerability_id=document["vulnerability_id"],
        target_name=document.get("target_name"),
        affected_versions=list(document.get("affected_versions", [])),
        fixed_versions=list(document.get("fixed_versions", [])),
        matched_queries=list(document.get("matched_queries", [])),
        evidence_sources=list(document.get("evidence_sources", [])),
        first_seen_at=document["first_seen_at"],
        last_seen_at=document["last_seen_at"],
    )


def _as_collection(db_or_collection: Any, collection_name: str) -> Any:
    type_name = type(db_or_collection).__name__
    if type_name == "Collection":
        return db_or_collection
    return getattr(db_or_collection, collection_name)


def _return_document_after() -> Any:
    if ReturnDocument is None:
        raise RuntimeError("pymongo is required to use MongoDB repositories")
    return ReturnDocument.AFTER


class MongoDatabase:
    def __init__(self, uri: str = "mongodb://localhost:27017", database: str = "pwn2own_updater") -> None:
        if MongoClient is None:
            raise RuntimeError("pymongo is required to use MongoDatabase")
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[database]
        self.ensure_indexes()

    def ensure_indexes(self) -> None:
        self.db.targets.create_index("normalized_name", unique=True)
        self.db.target_versions.create_index(
            [("target_id", ASCENDING), ("version", ASCENDING), ("version_type", ASCENDING)],
            unique=True,
            partialFilterExpression={"version": {"$type": "string"}},
        )
        self.db.vulnerabilities.create_index("advisory_id", unique=True)
        self.db.target_vulnerabilities.create_index(
            [("target_id", ASCENDING), ("vulnerability_id", ASCENDING)],
            unique=True,
        )


class MongoTargetRepository:
    def __init__(self, db: Any) -> None:
        self.collection = _as_collection(db, "targets")

    def upsert(self, target: Target) -> Target:
        document = target_to_document(target)
        created_at = document.pop("created_at")
        updated = self.collection.find_one_and_update(
            {"normalized_name": document["normalized_name"]},
            {"$set": document, "$setOnInsert": {"created_at": created_at}},
            upsert=True,
            return_document=_return_document_after(),
        )
        return target_from_document(updated)

    def list_all(self) -> list[Target]:
        return [target_from_document(document) for document in self.collection.find().sort("normalized_name", ASCENDING)]

    def find_by_name(self, name: str) -> Target | None:
        document = self.collection.find_one({"normalized_name": normalize_name(name)})
        return target_from_document(document) if document else None

    def delete_all(self) -> int:
        return self.collection.delete_many({}).deleted_count


class MongoTargetVersionRepository:
    def __init__(self, db: Any) -> None:
        self.collection = _as_collection(db, "target_versions")

    def upsert(self, version: TargetVersion) -> TargetVersion:
        document = target_version_to_document(version)
        first_seen_at = document.pop("first_seen_at")
        updated = self.collection.find_one_and_update(
            {
                "target_id": document["target_id"],
                "version": document["version"],
                "version_type": document["version_type"],
            },
            {"$set": document, "$setOnInsert": {"first_seen_at": first_seen_at}},
            upsert=True,
            return_document=_return_document_after(),
        )
        return target_version_from_document(updated)

    def delete_all(self) -> int:
        return self.collection.delete_many({}).deleted_count


class MongoVulnerabilityRepository:
    def __init__(self, db: Any) -> None:
        self.collection = _as_collection(db, "vulnerabilities")

    def upsert(self, vulnerability: Vulnerability) -> Vulnerability:
        document = vulnerability_to_document(vulnerability)
        created_at = document.pop("created_at")
        existing = self.collection.find_one({"advisory_id": document["advisory_id"]})
        if existing is not None:
            merged = merge_vulnerability_documents(existing, document)
            self.collection.replace_one(
                {"advisory_id": document["advisory_id"]}, merged
            )
            return vulnerability_from_document(merged)
        document["created_at"] = created_at
        self.collection.insert_one(document)
        return vulnerability_from_document(document)

    def list_all(self) -> list[Vulnerability]:
        return [vulnerability_from_document(document) for document in self.collection.find().sort("advisory_id", ASCENDING)]

    def delete_all(self) -> int:
        return self.collection.delete_many({}).deleted_count


def merge_vulnerability_documents(
    existing: dict[str, Any], incoming: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(existing)

    for key in ("sources", "aliases", "references"):
        existing_list: list = list(merged.get(key, []))
        incoming_list: list = incoming.get(key, []) or []
        seen = set()
        combined: list = []
        for item in existing_list + incoming_list:
            if item not in seen:
                seen.add(item)
                combined.append(item)
        merged[key] = combined

    existing_raw: dict = dict(merged.get("raw", {}) or {})
    incoming_raw: dict = incoming.get("raw", {}) or {}
    existing_raw.update(incoming_raw)
    merged["raw"] = existing_raw

    existing_desc = merged.get("description") or ""
    incoming_desc = incoming.get("description") or ""
    combined_sources = set(merged.get("sources", [])) | set(incoming.get("sources", []))
    if "zdi" in combined_sources:
        zdi_desc = incoming_desc if "zdi" in (incoming.get("sources", []) or []) else existing_desc
        nvd_desc = incoming_desc if zdi_desc != incoming_desc else existing_desc
        merged["description"] = zdi_desc or nvd_desc
    elif incoming_desc:
        merged["description"] = incoming_desc
    else:
        merged["description"] = existing_desc

    for key in ("cvss_score", "severity", "published_date", "updated_at"):
        if incoming.get(key) is not None:
            merged[key] = incoming[key]

    return merged


class MongoTargetVulnerabilityRepository:
    def __init__(self, db: Any) -> None:
        self.collection = _as_collection(db, "target_vulnerabilities")

    def upsert(self, link: TargetVulnerability) -> TargetVulnerability:
        document = target_vulnerability_to_document(link)
        first_seen_at = document.pop("first_seen_at")
        updated = self.collection.find_one_and_update(
            {"target_id": document["target_id"], "vulnerability_id": document["vulnerability_id"]},
            {"$set": document, "$setOnInsert": {"first_seen_at": first_seen_at}},
            upsert=True,
            return_document=_return_document_after(),
        )
        return target_vulnerability_from_document(updated)

    def list_all(self) -> list[TargetVulnerability]:
        return [target_vulnerability_from_document(document) for document in self.collection.find()]

    def delete_all(self) -> int:
        return self.collection.delete_many({}).deleted_count