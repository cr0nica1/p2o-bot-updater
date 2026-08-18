from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from updater.infrastructure.mongo import MongoTargetVersionRepository


class FakeVersionCollection:
    """Minimal in-memory stand-in for the target_versions collection."""

    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def _match(self, doc, query):
        for key, cond in query.items():
            actual = doc.get(key)
            if isinstance(cond, dict):
                if "$ne" in cond and actual == cond["$ne"]:
                    return False
                if "$gte" in cond and not (actual is not None and actual >= cond["$gte"]):
                    return False
            elif actual != cond:
                return False
        return True

    def find_one(self, query):
        return next((d for d in self.docs if self._match(d, query)), None)

    def find(self, query):
        return [d for d in self.docs if self._match(d, query)]

    def update_many(self, query, update):
        for d in self.docs:
            if self._match(d, query):
                d.update(update["$set"])

    def update_one(self, query, update):
        d = self.find_one(query)
        if d is not None:
            d.update(update["$set"])

    def find_one_and_update(self, query, update, upsert=False, return_document=None):
        d = self.find_one(query)
        if d is None:
            if not upsert:
                return None
            d = dict(query)
            d.update(update.get("$setOnInsert", {}))
            self.docs.append(d)
        d.update(update.get("$set", {}))
        return d


def _repo(docs=None):
    coll = FakeVersionCollection(docs)
    # _as_collection() only special-cases real pymongo Collection objects by class
    # name; anything else it treats as a db and does getattr(db, "target_versions").
    # Construct with a stand-in that has that attribute, then swap in the fake.
    repo = MongoTargetVersionRepository(SimpleNamespace(target_versions=coll))
    repo.collection = coll
    return repo, coll


def test_set_current_seeds_and_marks_latest():
    repo, _ = _repo()
    repo.set_current("t1", version="1.0.0", source_url="https://x", previous_version=None)
    latest = repo.find_latest("t1")
    assert latest is not None
    assert latest.version == "1.0.0"
    assert latest.is_latest is True
    assert latest.previous_version is None


def test_set_current_change_demotes_prior_and_records_previous():
    repo, coll = _repo()
    repo.set_current("t1", version="1.0.0", source_url="https://x", previous_version=None)
    repo.set_current("t1", version="1.1.0", source_url="https://x", previous_version="1.0.0")
    latest = repo.find_latest("t1")
    assert latest.version == "1.1.0"
    assert latest.previous_version == "1.0.0"
    old = next(d for d in coll.docs if d["version"] == "1.0.0")
    assert old["is_latest"] is False


def test_mark_seen_updates_last_seen_only():
    repo, coll = _repo()
    repo.set_current("t1", version="1.0.0", source_url="https://x", previous_version=None)
    before = next(d for d in coll.docs if d["version"] == "1.0.0")["last_seen_at"]
    repo.mark_seen("t1", version="1.0.0")
    doc = next(d for d in coll.docs if d["version"] == "1.0.0")
    assert doc["last_seen_at"] >= before
    assert doc["is_latest"] is True
    assert doc["previous_version"] is None


def test_list_recent_changes_filters_by_window_and_previous():
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    old = now - timedelta(days=2)
    docs = [
        {"target_id": "a", "version": "2.0", "version_type": None, "is_latest": True,
         "previous_version": "1.0", "first_seen_at": now, "last_seen_at": now, "raw": {}, "source_url": "u"},
        {"target_id": "b", "version": "3.0", "version_type": None, "is_latest": True,
         "previous_version": None, "first_seen_at": now, "last_seen_at": now, "raw": {}, "source_url": "u"},
        {"target_id": "c", "version": "4.0", "version_type": None, "is_latest": True,
         "previous_version": "3.9", "first_seen_at": old, "last_seen_at": old, "raw": {}, "source_url": "u"},
    ]
    repo, _ = _repo(docs)
    since = now - timedelta(hours=1)
    changed = repo.list_recent_changes(since)
    ids = {v.target_id for v in changed}
    assert ids == {"a"}  # b has no previous_version; c is before the window
