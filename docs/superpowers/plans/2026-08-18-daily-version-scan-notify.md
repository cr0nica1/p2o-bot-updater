# Daily Version Scan + Discord Notify Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scan every target's version checker once per day and post a Discord notification whenever a target's version changes.

**Architecture:** A new `VersionScanService` (application layer) runs each of the ten target-bound version checkers via the existing `FirmwareLookupService`, compares each result against the stored current version in `TargetVersion`, persists changes, and returns a report. The scan folds into the existing daily `sync` event and the change report into the existing `notify` event in `bot.py` — no `FireTracker` change, no new config. An admin `/scan-versions` command runs it on demand.

**Tech Stack:** Python 3.12, dataclasses, pymongo, discord.py, pytest. Run tests with `python3 -m pytest` (there is NO `python` on PATH; deps are installed with `--break-system-packages`; pytest lives at `~/.local/bin`).

**Spec:** `docs/superpowers/specs/2026-08-18-daily-version-scan-notify-design.md` (read it alongside this plan).

## Global Constraints

- **Env:** use `python3`, never `python`. Run the suite with `python3 -m pytest -q`. Baseline before Task 1 is **234 passed**.
- **No new config / no new schedule / no `FireTracker` change.** Reuse `sync_time`, `notify_time`, `channel_id`, tz. The scan rides inside `_run_sync`; the report inside `_run_notify`.
- **Scope:** the scan covers only target-bound version checkers — a target is in scope iff `vendor_config_repo.find_by_target(target)` returns a config. Legacy per-vendor firmware is out of scope.
- **Notify only on change; seed silently.** First scan of a target records a baseline with `previous_version=None` and is never announced. Only a differing version is announced.
- **Enumeration order must match `FirmwareLookupService`:** targets are enumerated `sorted(target_repo.list_all(), key=lambda t: t.name.casefold())`, 1-based, so the index passed to `lookup(target_id)` resolves to the same target.
- **Per-target failure isolation:** a single target's lookup error is logged and recorded in `report.errors`; it never aborts the scan.
- **`version_type` for scan-produced versions is `None`** (the compound key `(target_id, version, None)` is valid).
- **Backward compatibility:** the new `TargetVersion.previous_version` field defaults `None` and loads from old documents via `.get(...)`. All existing tests stay green.
- No new third-party dependencies.

## File Structure

- `src/updater/domain/models.py` — add `previous_version` to `TargetVersion`; add `Target.storage_id` property.
- `src/updater/domain/repositories.py` — extend `TargetVersionRepository` protocol.
- `src/updater/infrastructure/mongo.py` — map `previous_version`; implement the four new repo methods on `MongoTargetVersionRepository`.
- `src/updater/application/version_scan.py` — **new**: `VersionChange`, `VersionScanReport`, `VersionScanService`, `version_changes_from_docs`.
- `src/updater/presentation/discord_bot/formatting.py` — add `build_version_update_message`.
- `src/updater/presentation/discord_bot/commands.py` — add `handle_scan_versions`.
- `src/updater/presentation/discord_bot/bot.py` — wire scan into `_run_sync`, report into `_run_notify`, register `/scan-versions`.

Tests: `tests/domain/test_models.py`, `tests/infrastructure/test_mongo_mapping.py`, `tests/infrastructure/test_target_version_repo.py` (new), `tests/application/test_version_scan.py` (new), `tests/presentation/discord_bot/test_formatting.py`, `tests/presentation/discord_bot/test_commands.py`.

---

### Task 1: `TargetVersion.previous_version` field + Mongo mapping

**Files:**
- Modify: `src/updater/domain/models.py` (`TargetVersion`)
- Modify: `src/updater/infrastructure/mongo.py` (`target_version_to_document`, `target_version_from_document`)
- Test: `tests/domain/test_models.py`, `tests/infrastructure/test_mongo_mapping.py`

**Interfaces:**
- Produces: `TargetVersion.previous_version: str | None = None`; the document round-trip preserves it and defaults `None` for legacy documents.

- [ ] **Step 1: Write the failing tests**

In `tests/domain/test_models.py` (append):

```python
def test_target_version_previous_version_defaults_to_none():
    from updater.domain.models import TargetVersion
    assert TargetVersion().previous_version is None
    assert TargetVersion(previous_version="1.0.0").previous_version == "1.0.0"
```

In `tests/infrastructure/test_mongo_mapping.py` (append; `TargetVersion` is already importable from `updater.domain.models`, add it to the existing import there):

```python
def test_target_version_document_round_trips_previous_version():
    from updater.domain.models import TargetVersion
    from updater.infrastructure.mongo import (
        target_version_from_document,
        target_version_to_document,
    )
    version = TargetVersion(target_id="t1", version="1.1.0", previous_version="1.0.0")
    document = target_version_to_document(version)
    assert document["previous_version"] == "1.0.0"
    # legacy documents without the field load as None
    legacy = dict(document)
    del legacy["previous_version"]
    assert target_version_from_document(legacy).previous_version is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/domain/test_models.py::test_target_version_previous_version_defaults_to_none tests/infrastructure/test_mongo_mapping.py::test_target_version_document_round_trips_previous_version -v`
Expected: FAIL (`TypeError: unexpected keyword argument 'previous_version'` / `KeyError`).

- [ ] **Step 3: Add the field and mapping**

In `src/updater/domain/models.py`, add to `TargetVersion` immediately after `is_latest`:

```python
    is_latest: bool | None = None
    previous_version: str | None = None
```

In `src/updater/infrastructure/mongo.py`, in `target_version_to_document` add `"previous_version": version.previous_version,` (put it right after the `"is_latest"` entry), and in `target_version_from_document` add `previous_version=document.get("previous_version"),` (right after the `is_latest=...` line).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/domain/test_models.py tests/infrastructure/test_mongo_mapping.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/domain/models.py src/updater/infrastructure/mongo.py tests/domain/test_models.py tests/infrastructure/test_mongo_mapping.py
git commit -m "feat: add TargetVersion.previous_version field and mapping"
```

---

### Task 2: `TargetVersionRepository` scan methods

**Files:**
- Modify: `src/updater/domain/repositories.py` (`TargetVersionRepository` protocol)
- Modify: `src/updater/infrastructure/mongo.py` (`MongoTargetVersionRepository`)
- Test: `tests/infrastructure/test_target_version_repo.py` (new)

**Interfaces:**
- Consumes: `TargetVersion.previous_version` (Task 1).
- Produces (all keyed on `version_type=None`):
  - `find_latest(target_id: str) -> TargetVersion | None`
  - `set_current(target_id: str, *, version: str, source_url: str | None, previous_version: str | None) -> TargetVersion`
  - `mark_seen(target_id: str, *, version: str) -> None`
  - `list_recent_changes(since: datetime) -> list[TargetVersion]`

- [ ] **Step 1: Write the failing tests**

Create `tests/infrastructure/test_target_version_repo.py`:

```python
from datetime import datetime, timedelta, timezone

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
    repo = MongoTargetVersionRepository(coll)
    repo.collection = coll  # _as_collection returns a collection-shaped object as-is
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/infrastructure/test_target_version_repo.py -v`
Expected: FAIL (`AttributeError: 'MongoTargetVersionRepository' object has no attribute 'find_latest'`).

- [ ] **Step 3: Extend the protocol and implement the methods**

In `src/updater/domain/repositories.py`, extend `TargetVersionRepository`:

```python
class TargetVersionRepository(Protocol):
    def upsert(self, version: TargetVersion) -> TargetVersion: ...
    def delete_all(self) -> int: ...
    def find_latest(self, target_id: str) -> TargetVersion | None: ...
    def set_current(
        self, target_id: str, *, version: str, source_url: str | None, previous_version: str | None
    ) -> TargetVersion: ...
    def mark_seen(self, target_id: str, *, version: str) -> None: ...
    def list_recent_changes(self, since: datetime) -> list[TargetVersion]: ...
```

Ensure `datetime` is imported in `repositories.py` (add `from datetime import datetime` if missing).

In `src/updater/infrastructure/mongo.py`, add these methods to `MongoTargetVersionRepository` (import `utc_now` from `updater.domain.models` — it is already the module the mongo mappers import models from; add it to that import):

```python
    def find_latest(self, target_id):
        document = self.collection.find_one({"target_id": target_id, "is_latest": True})
        return target_version_from_document(document) if document else None

    def set_current(self, target_id, *, version, source_url, previous_version):
        self.collection.update_many(
            {"target_id": target_id, "is_latest": True},
            {"$set": {"is_latest": False}},
        )
        now = utc_now()
        document = self.collection.find_one_and_update(
            {"target_id": target_id, "version": version, "version_type": None},
            {
                "$set": {
                    "is_latest": True,
                    "previous_version": previous_version,
                    "source_url": source_url,
                    "version_type": None,
                    "last_seen_at": now,
                    "raw": {},
                },
                "$setOnInsert": {"first_seen_at": now},
            },
            upsert=True,
            return_document=_return_document_after(),
        )
        return target_version_from_document(document)

    def mark_seen(self, target_id, *, version):
        self.collection.update_one(
            {"target_id": target_id, "version": version, "version_type": None},
            {"$set": {"last_seen_at": utc_now()}},
        )

    def list_recent_changes(self, since):
        cursor = self.collection.find(
            {
                "is_latest": True,
                "previous_version": {"$ne": None},
                "first_seen_at": {"$gte": since},
            }
        )
        return [target_version_from_document(document) for document in cursor]
```

`target_version_from_document` reads `first_seen_at`/`last_seen_at` with `document[...]`; the fake seeds both, and `set_current`'s `$setOnInsert`/`$set` provide both on insert, so the round-trip is safe.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/infrastructure/test_target_version_repo.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/domain/repositories.py src/updater/infrastructure/mongo.py tests/infrastructure/test_target_version_repo.py
git commit -m "feat: add find_latest/set_current/mark_seen/list_recent_changes to version repo"
```

---

### Task 3: `VersionScanService` + `Target.storage_id` + `version_changes_from_docs`

**Files:**
- Create: `src/updater/application/version_scan.py`
- Modify: `src/updater/domain/models.py` (add `Target.storage_id`)
- Test: `tests/application/test_version_scan.py` (new)

**Interfaces:**
- Consumes: `FirmwareLookupService.lookup(target_id)` → `FirmwareLookupResult(version, resolved_url, ...)`; `FirmwareLookupError`; `HttpFetchError`/`BrowserLaunchError` from `updater.infrastructure.browser`; the Task 2 repo methods; `vendor_config_repo.find_by_target(target)`.
- Produces:
  - `Target.storage_id -> str` (`self.id or self.normalized_name`)
  - `VersionChange(target_name, old_version, new_version, source_url)` (frozen dataclass)
  - `VersionScanReport(changes, seeded, unchanged, errors)` with `.scanned` property
  - `VersionScanService(target_repo, vendor_config_repo, version_repo, lookup_service)` with `scan_all() -> VersionScanReport`
  - `version_changes_from_docs(docs, targets) -> list[VersionChange]`

- [ ] **Step 1: Write the failing tests**

Create `tests/application/test_version_scan.py`:

```python
from updater.application.firmware_lookup import FirmwareLookupError, FirmwareLookupResult
from updater.application.version_scan import (
    VersionChange,
    VersionScanService,
    version_changes_from_docs,
)
from updater.domain.models import Target, TargetVersion, VendorConfig


class FakeTargetRepo:
    def __init__(self, targets):
        self._targets = list(targets)

    def list_all(self):
        return list(self._targets)


class FakeVendorConfigRepo:
    def __init__(self, bound_names):
        self._bound = set(bound_names)

    def find_by_target(self, target):
        if target.name in self._bound:
            return VendorConfig(vendor=target.name, target=target.name,
                                url_template="https://x/releases", fetch="http",
                                regex=r"v(\d+\.\d+\.\d+)", select="first")
        return None


class FakeVersionRepo:
    def __init__(self, latest=None):
        self.latest = dict(latest or {})   # storage_id -> TargetVersion
        self.marked = []
        self.set_calls = []

    def find_latest(self, target_id):
        return self.latest.get(target_id)

    def set_current(self, target_id, *, version, source_url, previous_version):
        tv = TargetVersion(target_id=target_id, version=version, source_url=source_url,
                           previous_version=previous_version, is_latest=True)
        self.latest[target_id] = tv
        self.set_calls.append((target_id, version, previous_version))
        return tv

    def mark_seen(self, target_id, *, version):
        self.marked.append((target_id, version))


class FakeLookup:
    """lookup(target_id) -> result or raises, keyed by 1-based sorted index."""

    def __init__(self, by_id):
        self.by_id = by_id

    def lookup(self, target_id):
        outcome = self.by_id[target_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _result(version, url="https://x/releases"):
    return FirmwareLookupResult(target_name="", vendor="", resolved_url=url,
                                version=version, download_url=None, html_snippet="")


def test_first_scan_seeds_silently():
    targets = [Target(name="Chroma", id="c1")]
    repo = FakeVersionRepo()
    service = VersionScanService(FakeTargetRepo(targets), FakeVendorConfigRepo({"Chroma"}),
                                 repo, FakeLookup({1: _result("1.6.0")}))
    report = service.scan_all()
    assert report.changes == []
    assert report.seeded == ["Chroma"]
    assert repo.latest["c1"].version == "1.6.0"
    assert repo.latest["c1"].previous_version is None


def test_changed_version_is_reported_and_persisted():
    targets = [Target(name="Chroma", id="c1")]
    repo = FakeVersionRepo(latest={"c1": TargetVersion(target_id="c1", version="1.5.9")})
    service = VersionScanService(FakeTargetRepo(targets), FakeVendorConfigRepo({"Chroma"}),
                                 repo, FakeLookup({1: _result("1.6.0")}))
    report = service.scan_all()
    assert report.changes == [VersionChange("Chroma", "1.5.9", "1.6.0", "https://x/releases")]
    assert repo.set_calls == [("c1", "1.6.0", "1.5.9")]


def test_unchanged_version_marks_seen():
    targets = [Target(name="Chroma", id="c1")]
    repo = FakeVersionRepo(latest={"c1": TargetVersion(target_id="c1", version="1.6.0")})
    service = VersionScanService(FakeTargetRepo(targets), FakeVendorConfigRepo({"Chroma"}),
                                 repo, FakeLookup({1: _result("1.6.0")}))
    report = service.scan_all()
    assert report.unchanged == ["Chroma"]
    assert report.changes == []
    assert repo.marked == [("c1", "1.6.0")]


def test_lookup_error_is_isolated_and_others_still_scan():
    # sorted by casefold: "Alpha" (id=1), "Zeta" (id=2)
    targets = [Target(name="Zeta", id="z1"), Target(name="Alpha", id="a1")]
    repo = FakeVersionRepo()
    lookup = FakeLookup({1: FirmwareLookupError("boom"), 2: _result("2.0.0")})
    service = VersionScanService(FakeTargetRepo(targets), FakeVendorConfigRepo({"Alpha", "Zeta"}),
                                 repo, lookup)
    report = service.scan_all()
    assert report.errors == [("Alpha", "boom")]
    assert report.seeded == ["Zeta"]


def test_targets_without_bound_config_are_skipped():
    targets = [Target(name="Chroma", id="c1"), Target(name="Legacy", id="l1")]
    repo = FakeVersionRepo()
    service = VersionScanService(FakeTargetRepo(targets), FakeVendorConfigRepo({"Chroma"}),
                                 repo, FakeLookup({1: _result("1.6.0")}))
    report = service.scan_all()
    assert report.seeded == ["Chroma"]
    assert "Legacy" not in report.seeded + report.unchanged


def test_version_changes_from_docs_resolves_names_and_skips_unknown():
    targets = [Target(name="Chroma", id="c1")]
    docs = [
        TargetVersion(target_id="c1", version="1.6.0", previous_version="1.5.9", source_url="u"),
        TargetVersion(target_id="ghost", version="9.9", previous_version="9.8", source_url="u"),
    ]
    changes = version_changes_from_docs(docs, targets)
    assert changes == [VersionChange("Chroma", "1.5.9", "1.6.0", "u")]
```

Note the error test: `"Alpha"` sorts before `"Zeta"` (casefold), so `lookup(1)` is Alpha and `lookup(2)` is Zeta — matching the `FakeLookup` keys.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/application/test_version_scan.py -v`
Expected: FAIL (`ModuleNotFoundError: updater.application.version_scan`).

- [ ] **Step 3: Add `Target.storage_id` and create the service**

In `src/updater/domain/models.py`, add to `Target` (after the `normalized_name` property):

```python
    @property
    def storage_id(self) -> str:
        return self.id or self.normalized_name
```

Create `src/updater/application/version_scan.py`:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from updater.application.firmware_lookup import FirmwareLookupError
from updater.domain.models import Target, TargetVersion
from updater.infrastructure.browser import BrowserLaunchError, HttpFetchError

log = logging.getLogger("updater.version_scan")


@dataclass(frozen=True)
class VersionChange:
    target_name: str
    old_version: str
    new_version: str
    source_url: str


@dataclass(frozen=True)
class VersionScanReport:
    changes: list[VersionChange]
    seeded: list[str]
    unchanged: list[str]
    errors: list[tuple[str, str]]

    @property
    def scanned(self) -> int:
        return len(self.changes) + len(self.seeded) + len(self.unchanged)


class VersionScanService:
    def __init__(self, target_repo, vendor_config_repo, version_repo, lookup_service) -> None:
        self.target_repo = target_repo
        self.vendor_config_repo = vendor_config_repo
        self.version_repo = version_repo
        self.lookup_service = lookup_service

    def scan_all(self) -> VersionScanReport:
        changes: list[VersionChange] = []
        seeded: list[str] = []
        unchanged: list[str] = []
        errors: list[tuple[str, str]] = []

        targets = sorted(self.target_repo.list_all(), key=lambda t: t.name.casefold())
        for target_id, target in enumerate(targets, start=1):
            config = self.vendor_config_repo.find_by_target(target)
            if config is None:
                continue
            try:
                result = self.lookup_service.lookup(target_id)
            except (FirmwareLookupError, HttpFetchError, BrowserLaunchError) as exc:
                log.warning("version scan failed for %s: %s", target.name, exc)
                errors.append((target.name, str(exc)))
                continue

            storage_id = target.storage_id
            new_version = result.version
            current = self.version_repo.find_latest(storage_id)
            if current is None:
                self.version_repo.set_current(
                    storage_id, version=new_version,
                    source_url=result.resolved_url, previous_version=None,
                )
                seeded.append(target.name)
            elif current.version != new_version:
                self.version_repo.set_current(
                    storage_id, version=new_version,
                    source_url=result.resolved_url, previous_version=current.version,
                )
                changes.append(
                    VersionChange(target.name, current.version, new_version, result.resolved_url)
                )
            else:
                self.version_repo.mark_seen(storage_id, version=new_version)
                unchanged.append(target.name)

        return VersionScanReport(changes=changes, seeded=seeded, unchanged=unchanged, errors=errors)


def version_changes_from_docs(
    docs: list[TargetVersion], targets: list[Target]
) -> list[VersionChange]:
    names = {t.storage_id: t.name for t in targets}
    changes: list[VersionChange] = []
    for doc in docs:
        name = names.get(doc.target_id)
        if name is None:
            continue
        changes.append(
            VersionChange(name, doc.previous_version or "", doc.version or "", doc.source_url or "")
        )
    return changes
```

(`datetime` import is retained for readers/type context even though it is not referenced directly; remove it if your linter objects.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/application/test_version_scan.py tests/domain/test_models.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/application/version_scan.py src/updater/domain/models.py tests/application/test_version_scan.py
git commit -m "feat: add VersionScanService with change detection and doc mapping"
```

---

### Task 4: `build_version_update_message`

**Files:**
- Modify: `src/updater/presentation/discord_bot/formatting.py`
- Test: `tests/presentation/discord_bot/test_formatting.py`

**Interfaces:**
- Consumes: `VersionChange` (Task 3) — duck-typed via `.target_name`, `.old_version`, `.new_version`.
- Produces: `build_version_update_message(*, report_date: date, changes) -> str`.

- [ ] **Step 1: Write the failing test**

In `tests/presentation/discord_bot/test_formatting.py` (append; ensure `from datetime import date` is present):

```python
def test_build_version_update_message_lists_changes_and_count():
    from datetime import date
    from updater.application.version_scan import VersionChange
    from updater.presentation.discord_bot.formatting import build_version_update_message

    msg = build_version_update_message(
        report_date=date(2026, 8, 18),
        changes=[
            VersionChange("Chroma", "1.5.9", "1.6.0", "u"),
            VersionChange("LiteLLM", "v1.97.0", "v1.98.0", "u"),
        ],
    )
    assert "🔔 Version updates — 2026-08-18" in msg
    assert "• Chroma: 1.5.9 → 1.6.0" in msg
    assert "• LiteLLM: v1.97.0 → v1.98.0" in msg
    assert "2 update(s)" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/presentation/discord_bot/test_formatting.py::test_build_version_update_message_lists_changes_and_count -v`
Expected: FAIL (`ImportError`/`AttributeError`).

- [ ] **Step 3: Implement the formatter**

In `src/updater/presentation/discord_bot/formatting.py` add (near `build_summary_message`; `date` is already imported there):

```python
def build_version_update_message(*, report_date: date, changes) -> str:
    lines = [f"🔔 Version updates — {report_date.isoformat()}"]
    for change in changes:
        lines.append(f"• {change.target_name}: {change.old_version} → {change.new_version}")
    lines.append(f"{len(changes)} update(s)")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/presentation/discord_bot/test_formatting.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/presentation/discord_bot/formatting.py tests/presentation/discord_bot/test_formatting.py
git commit -m "feat: add build_version_update_message formatter"
```

---

### Task 5: `/scan-versions` command handler

**Files:**
- Modify: `src/updater/presentation/discord_bot/commands.py`
- Test: `tests/presentation/discord_bot/test_commands.py`

**Interfaces:**
- Consumes: `Services` (has `target_repo`, `vendor_config_repo`, `version_repo`, `browser`, `http`); `FirmwareLookupService` (already imported in `commands.py`); `VersionScanService` (Task 3); `build_version_update_message` (Task 4).
- Produces: `async handle_scan_versions(services: Services) -> CommandResult`.

**Carry-forward:** the module-level `FakeVersionRepo` in `test_commands.py` currently has only `upsert`/`delete_all`. Extend it (in this task's test step) with `find_latest`, `set_current`, `mark_seen` so the real `VersionScanService` runs against it. Do not remove `upsert`/`delete_all`.

- [ ] **Step 1: Write the failing test**

First extend the module-level `FakeVersionRepo` in `tests/presentation/discord_bot/test_commands.py`:

```python
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
```

Add `handle_scan_versions` to the imports from `updater.presentation.discord_bot.commands` at the top of the file. Then append the tests:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/presentation/discord_bot/test_commands.py -k scan_versions -v`
Expected: FAIL (`ImportError: cannot import name 'handle_scan_versions'`).

- [ ] **Step 3: Implement the handler**

In `src/updater/presentation/discord_bot/commands.py`:
- Add to the `updater.application.firmware_lookup` import: `FirmwareLookupService` is already imported. Add a new import `from updater.application.version_scan import VersionScanService`.
- Add `build_version_update_message` to the existing `from updater.presentation.discord_bot.formatting import (...)` block.
- Append the handler:

```python
async def handle_scan_versions(services: Services) -> CommandResult:
    lookup = FirmwareLookupService(
        services.target_repo, services.vendor_config_repo, services.browser, services.http
    )
    scan = VersionScanService(
        services.target_repo, services.vendor_config_repo, services.version_repo, lookup
    )
    report = await asyncio.to_thread(scan.scan_all)
    today = datetime.now(timezone.utc).date()
    footer = f"scanned {report.scanned}, {len(report.errors)} error(s)"
    if report.changes:
        body = build_version_update_message(report_date=today, changes=report.changes)
        return CommandResult(text=f"{body}\n{footer}")
    return CommandResult(text=f"No version updates.\n{footer}")
```

(`asyncio`, `datetime`, `timezone`, `FirmwareLookupService`, `CommandResult` are already imported in `commands.py`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/presentation/discord_bot/test_commands.py -q`
Expected: PASS (all existing command tests plus the two new ones).

- [ ] **Step 5: Commit**

```bash
git add src/updater/presentation/discord_bot/commands.py tests/presentation/discord_bot/test_commands.py
git commit -m "feat: add /scan-versions command handler"
```

---

### Task 6: Bot wiring — scan in `_run_sync`, report in `_run_notify`, register `/scan-versions`

**Files:**
- Modify: `src/updater/presentation/discord_bot/bot.py`
- Test: `tests/presentation/discord_bot/test_bot_version_notify.py` (new)

**Interfaces:**
- Consumes: `VersionScanService`, `version_changes_from_docs` (Task 3); `build_version_update_message` (Task 4); `handle_scan_versions` (Task 5); `services.version_repo.list_recent_changes` (Task 2).
- Produces: version scan on the `sync` event; version notification on the `notify` event; `/scan-versions` slash command.

**Note on testing the glue:** `_run_sync`/`_run_notify`/`build_client` are async discord glue with no existing test harness (see `test_scheduler.py`, which covers only `FireTracker`). Keep the bot edits thin; the meaningful logic lives in the already-tested `version_changes_from_docs` + `build_version_update_message`. This task's test covers the notify composition (docs → changes → message / empty → nothing) as a pure pipeline, without discord.

- [ ] **Step 1: Write the failing test**

Create `tests/presentation/discord_bot/test_bot_version_notify.py`:

```python
from datetime import date

from updater.application.version_scan import version_changes_from_docs
from updater.domain.models import Target, TargetVersion
from updater.presentation.discord_bot.formatting import build_version_update_message


def test_notify_pipeline_builds_message_for_recent_changes():
    targets = [Target(name="Chroma", id="c1")]
    docs = [TargetVersion(target_id="c1", version="1.6.0", previous_version="1.5.9", source_url="u")]
    changes = version_changes_from_docs(docs, targets)
    assert changes  # non-empty → the bot posts a version section
    msg = build_version_update_message(report_date=date(2026, 8, 18), changes=changes)
    assert "• Chroma: 1.5.9 → 1.6.0" in msg


def test_notify_pipeline_is_empty_when_no_recent_changes():
    targets = [Target(name="Chroma", id="c1")]
    changes = version_changes_from_docs([], targets)
    assert changes == []  # empty → the bot posts no version section
```

- [ ] **Step 2: Run test to verify it fails / passes-by-construction**

Run: `python3 -m pytest tests/presentation/discord_bot/test_bot_version_notify.py -v`
Expected: PASS (these exercise already-built Task 3/4 functions; they are the regression guard for the wiring). If they fail, Task 3/4 regressed — fix before continuing.

- [ ] **Step 3: Wire the bot**

In `src/updater/presentation/discord_bot/bot.py`:

1. Add imports near the other application imports:

```python
from updater.application.version_scan import VersionScanService, version_changes_from_docs
```
and add `build_version_update_message` to the existing `from updater.presentation.discord_bot.formatting import (...)` block.

2. Add a field to `ScheduledSyncRun`:

```python
@dataclass
class ScheduledSyncRun:
    sync_started_at: datetime
    sync_result: object
    version_report: object = None
```

3. In `_run_sync`, after the existing CVE sync succeeds and before `return ScheduledSyncRun(...)`, run the scan and attach the report (a scan failure must not break the CVE sync):

```python
        version_report = None
        try:
            lookup = FirmwareLookupService(
                services.target_repo, services.vendor_config_repo, services.browser, services.http
            )
            version_report = await asyncio.to_thread(
                VersionScanService(
                    services.target_repo, services.vendor_config_repo,
                    services.version_repo, lookup,
                ).scan_all
            )
            log.info(
                "scheduled version scan done changes=%d seeded=%d errors=%d",
                len(version_report.changes), len(version_report.seeded), len(version_report.errors),
            )
        except Exception:
            log.exception("scheduled version scan failed")
        return ScheduledSyncRun(
            sync_started_at=sync_started_at, sync_result=result, version_report=version_report,
        )
```
`FirmwareLookupService` is already imported in `bot.py`? If not, add `from updater.application.firmware_lookup import FirmwareLookupService`. (It is currently imported in `commands.py`; add the import to `bot.py`.)

4. In `_run_notify`, after the existing findings loop, append a version section derived from the store (`tz` is already a parameter of `_run_notify`):

```python
    try:
        report_date = datetime.now(tz).date()
        window_start = datetime(report_date.year, report_date.month, report_date.day, tzinfo=tz)
        recent = await asyncio.to_thread(services.version_repo.list_recent_changes, window_start)
        targets = await asyncio.to_thread(services.target_repo.list_all)
        version_changes = version_changes_from_docs(recent, targets)
        if version_changes:
            await channel.send(
                content=build_version_update_message(report_date=report_date, changes=version_changes)
            )
    except Exception:
        log.exception("scheduled notify: version section failed")
```

5. Register the command next to `sync_cves` (admin-gated, background task, posts to the invoking channel):

```python
    @tree.command(name="scan-versions", description="Scan all version checkers now", guild=guild)
    async def scan_versions(interaction: discord.Interaction):
        if not await _admin_only(interaction):
            return
        channel = interaction.channel
        if channel is None:
            await interaction.response.send_message("Cannot run scan outside a channel.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Version scan started. Results will be posted in this channel when complete.",
            ephemeral=True,
        )

        async def _run_manual_scan() -> None:
            try:
                result = await cmd.handle_scan_versions(services)
                await _send_command_result(channel.send, result)
            except Exception:
                log.exception("manual version scan failed")
                await channel.send("Manual version scan failed. Check bot logs for details.")

        asyncio.create_task(_run_manual_scan())
```

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest -q`
Expected: PASS — all prior tests plus the new ones. Confirm the count increased and nothing regressed.

- [ ] **Step 5: Commit**

```bash
git add src/updater/presentation/discord_bot/bot.py tests/presentation/discord_bot/test_bot_version_notify.py
git commit -m "feat: run version scan in daily sync and post version updates on notify"
```

---

### Task 7: README documentation + full verification

**Files:**
- Modify: `README.md`
- Test: full suite

- [ ] **Step 1: Document the feature**

In `README.md`, in the "Target version checkers" section, append a short subsection:

```markdown
#### Daily scan and update notifications

The bot scans every target-bound version checker once per day, as part of the
existing daily sync/notify schedule (`/set-schedule`, `/show-schedule`). When a
target's version changes, it posts an update to the notify channel:

```
🔔 Version updates — 2026-08-18
• Chroma: 1.5.9 → 1.6.0
```

The first scan of each target records a baseline silently (no notification);
only later changes are announced. Run a scan on demand with `/scan-versions`
(admin only).
```

- [ ] **Step 2: Run the full suite**

Run: `python3 -m pytest -q`
Expected: PASS (whole suite green).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document daily version scan and update notifications"
```

---

## Self-Review

**1. Spec coverage:**
- Fold into sync/notify, no new config / no `FireTracker` change → Task 6 (scan in `_run_sync`, report in `_run_notify`). ✅
- Notify only on change, seed silently → Task 3 (`scan_all` seed/change/unchanged), Task 2 (`list_recent_changes` filters `previous_version != None`). ✅
- Manual `/scan-versions` → Task 5 (handler) + Task 6 (registration). ✅
- Scope = target-bound checkers only → Task 3 (`find_by_target is None → continue`). ✅
- `VersionScanService` + `VersionChange` + `VersionScanReport` → Task 3. ✅
- `TargetVersion.previous_version` + repo methods (`find_latest`/`set_current`/`mark_seen`/`list_recent_changes`) → Tasks 1–2. ✅
- Notification format + name resolution from storage id → Task 4 (`build_version_update_message`), Task 3 (`version_changes_from_docs`). ✅
- Error isolation → Task 3 (`test_lookup_error_is_isolated_and_others_still_scan`). ✅
- Backward compatibility (`previous_version` default None, `.get`) → Task 1. ✅
- Docs → Task 7. ✅

**2. Placeholder scan:** No TBD/TODO; every code and test step contains concrete content. ✅

**3. Type consistency:** `find_latest(target_id)`, `set_current(target_id, *, version, source_url, previous_version)`, `mark_seen(target_id, *, version)`, `list_recent_changes(since)` are used identically in Tasks 2, 3, 5, 6. `VersionChange(target_name, old_version, new_version, source_url)` and `VersionScanReport(changes, seeded, unchanged, errors)` are used identically across Tasks 3–6. `Target.storage_id` used in Tasks 3 and 6. `build_version_update_message(*, report_date, changes)` used identically in Tasks 4, 5, 6. ✅

## Execution Handoff

Plan complete. Recommended execution: **Subagent-Driven Development** (fresh subagent per task, task review after each, broad final review), matching how the version-checker feature itself was built.
