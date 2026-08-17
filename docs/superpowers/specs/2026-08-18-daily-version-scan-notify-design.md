# Daily version scan + Discord update notifications — design

**Date:** 2026-08-18
**Status:** Approved for planning
**Builds on:** `docs/superpowers/specs/2026-08-17-target-version-checkers-design.md` (the ten on-demand target version checkers)

## Goal

Automatically scan every target's version checker once per day, and post a
Discord notification whenever a target's version changes. This turns the
existing on-demand checkers (`/check-version`, `version-lookup`) into a
scheduled watch that reports updates without anyone asking.

## Approved decisions

1. **Fold into the existing daily sync/notify**, not a separate schedule. The
   scan runs inside the current `sync` event; version-change reporting runs
   inside the current `notify` event. Reuses `sync_time`, `notify_time`,
   `channel_id`, and the timezone — **no new config, no new schedule command,
   and no change to the `FireTracker` interface**.
2. **Notify only on change.** The first scan for a target seeds its baseline
   silently (no announcement). Subsequent scans announce only when the
   extracted version differs from the stored current version.
3. **Add a manual `/scan-versions` admin command** that runs the scan and posts
   the resulting changes immediately, mirroring `/sync-cves`.
4. **Scope: target-bound version checkers only** (the ten). A target is in
   scope when `vendor_config_repo.find_by_target(target)` returns a config.
   Legacy per-vendor firmware configs (which require a `vendor_alias`) are out
   of scope for the scheduled scan.

## Existing building blocks (reused, not rebuilt)

- `FirmwareLookupService.lookup(target_id)` — resolves the target-bound config,
  fetches (http/browser), extracts the version, returns `FirmwareLookupResult`
  (`version`, `resolved_url`, ...). The scan calls this per target.
- `TargetVersion` domain model — already stores version history keyed by
  `(target_id, version, version_type)` with `is_latest`, `first_seen_at`,
  `last_seen_at`. Change detection reuses this; see §3.
- `FireTracker` + `_scheduler_loop` (60s) + `_run_sync` / `_run_notify` in
  `bot.py` — the daily sync/notify machinery. The scan and report hook into
  `_run_sync` / `_run_notify` without changing `FireTracker`.
- `_target_storage_id(target) = target.id or target.normalized_name` — the
  identity used for `TargetVersion.target_id`. The scan uses the same helper
  (promote it from `commands.py` to a shared location if cleaner, or import it).

## Components

### 1. `VersionScanService` (application layer) — new

`src/updater/application/version_scan.py`

```python
@dataclass(frozen=True)
class VersionChange:
    target_name: str
    old_version: str
    new_version: str
    source_url: str

@dataclass(frozen=True)
class VersionScanReport:
    changes: list[VersionChange]
    seeded: list[str]      # target names baselined silently this run
    unchanged: list[str]   # target names whose version was already current
    errors: list[tuple[str, str]]  # (target_name, error message)

    @property
    def scanned(self) -> int:
        return len(self.changes) + len(self.seeded) + len(self.unchanged)
```

Constructor deps: `target_repo`, `vendor_config_repo`, `version_repo`, and a
`FirmwareLookupService` (or the pieces to build one). One public method:

```python
def scan_all(self) -> VersionScanReport
```

Algorithm — enumerate targets in the **same order the lookup service uses**
(`sorted(target_repo.list_all(), key=lambda t: t.name.casefold())`, 1-based
index), so the index passed to `lookup(target_id)` matches:

```
for target_id, target in enumerate(sorted_targets, start=1):
    config = vendor_config_repo.find_by_target(target)
    if config is None:
        continue                                   # not a version-check target
    try:
        result = lookup_service.lookup(target_id)  # reuse resolution/fetch/extract
    except (FirmwareLookupError, HttpFetchError, BrowserLaunchError) as exc:
        errors.append((target.name, str(exc)))
        continue
    storage_id = _target_storage_id(target)
    current = version_repo.find_latest(storage_id)
    new_version = result.version
    if current is None:
        version_repo.set_current(storage_id, version=new_version,
                                 source_url=result.resolved_url, previous_version=None)
        seeded.append(target.name)
    elif current.version != new_version:
        version_repo.set_current(storage_id, version=new_version,
                                 source_url=result.resolved_url,
                                 previous_version=current.version)
        changes.append(VersionChange(target.name, current.version, new_version,
                                     result.resolved_url))
    else:
        version_repo.mark_seen(storage_id, version=new_version)
        unchanged.append(target.name)
```

A single target's failure never aborts the scan — it is logged, added to
`errors`, and the loop continues. The service is synchronous (called via
`asyncio.to_thread` from the bot, like the existing sync).

### 2. `TargetVersionRepository` additions

`version_type` for scan-produced versions is `None` (the compound key
`(target_id, version, None)` is valid in Mongo). New protocol methods (+ Mongo
impl in `MongoTargetVersionRepository`):

- `find_latest(target_id: str) -> TargetVersion | None`
  → `find_one({"target_id": target_id, "is_latest": True})`.
- `set_current(target_id, *, version, source_url, previous_version) -> TargetVersion`
  Two steps: (a) demote — `update_many({"target_id", "is_latest": True}, {"$set": {"is_latest": False}})`; (b) upsert the new current —
  `find_one_and_update({"target_id","version","version_type": None}, {"$set": {is_latest True, previous_version, source_url, last_seen_at, ...}, "$setOnInsert": {first_seen_at}}, upsert=True, return after)`.
- `mark_seen(target_id, *, version) -> None`
  `update_one({"target_id","version","version_type": None}, {"$set": {"last_seen_at": now}})`. Does **not** touch `previous_version` or `is_latest`.

`TargetVersion` gains a first-class field `previous_version: str | None = None`
(model + `target_version_to_document` / `target_version_from_document` mapping,
the latter via `.get(...)` so existing docs load — backward compatible). This
makes the notify query explicit and avoids stuffing state into `raw`.

The existing `upsert`/`delete_all` methods are unchanged.

### 3. Scheduler integration (`bot.py`) — no `FireTracker` change

- `ScheduledSyncRun` gains `version_report: VersionScanReport | None`.
- `_run_sync`: after the CVE sync, build a `VersionScanService` from `services`
  and run `scan_all()` via `asyncio.to_thread`; attach the report to the
  returned `ScheduledSyncRun`. A scan failure is caught/logged and leaves
  `version_report=None` — it never breaks the CVE sync.
- `_run_notify`: after the existing CVE findings are posted, post a version
  section **derived from the store** (robust across separate sync/notify ticks):
  select current version docs (`is_latest=True`) with `previous_version` set and
  `first_seen_at >= window_start`, where `window_start` = start of the report
  date in the configured tz. `FireTracker` guarantees notify fires at most once
  per day, so each day's changes post exactly once. If the selection is empty,
  post **no** version section (silent). This needs one more read method:
  `list_recent_changes(since: datetime) -> list[TargetVersion]`
  → `find({"is_latest": True, "previous_version": {"$ne": None}, "first_seen_at": {"$gte": since}})`.
  The returned docs carry `target_id` (a storage id), not a display name, so the
  notify builds a `{_target_storage_id(t): t.name}` map from `target_repo.list_all()`
  and resolves each doc to a `VersionChange(name, doc.previous_version, doc.version,
  doc.source_url or "")` before formatting. A doc whose `target_id` no longer maps
  to a live target (target deleted) is skipped.

### 4. Notification format (`formatting.py`)

`build_version_update_message(report_date: date, changes: list[VersionChange]) -> str`
— one compact message (no per-target spam):

```
🔔 Version updates — 2026-08-18
• Chroma: 1.5.9 → 1.6.0
• LiteLLM: v1.97.0 → v1.98.0
2 update(s)
```

Input is uniformly `list[VersionChange]`. The scheduled path constructs the list
from `list_recent_changes` docs (resolving names as in §3); the manual path uses
`VersionScanReport.changes` directly. When there are no changes the scheduled path
posts nothing; the manual path posts `"No version updates."` plus a one-line count
of scanned/errors.

### 5. Manual command `/scan-versions` (`commands.py` + `bot.py`)

- `handle_scan_versions(services) -> CommandResult`: build the
  `VersionScanService` from `services`, run `scan_all()`, and return a
  `CommandResult` whose text is `build_version_update_message(today, report.changes)`
  when there are changes, else `"No version updates."`. Always append a compact
  footer: `"scanned N, M error(s)"` (list failing target names when `errors` is
  non-empty, truncated if long).
- `bot.py`: register `/scan-versions` admin-gated, mirroring `/sync-cves` — defer
  ephemerally, run in a background task, post the result to the invoking channel,
  and on exception post a failure line + log.

## Error handling

- Per-target lookup/extract failure → logged, added to `report.errors`, scan
  continues.
- Scan failure inside `_run_sync` → caught/logged, `version_report=None`, CVE
  sync unaffected.
- Notify send failures → wrapped in try/except and logged, matching the existing
  `_run_notify` sends.
- No new external dependencies.

## Testing

- **`VersionScanService.scan_all`** (fakes for repos + a fake lookup service):
  (a) first run seeds silently — `changes=[]`, `seeded` non-empty, nothing
  announced; (b) second run with a differing version yields one `VersionChange`
  (old→new) and persists the new current with `previous_version` set; (c) an
  unchanged version → `unchanged`, `mark_seen` called, `previous_version`
  untouched; (d) a target whose lookup raises → recorded in `errors`, other
  targets still scanned; (e) targets without a bound config are skipped.
- **Repo methods** (`find_latest`, `set_current` demote+upsert,
  `mark_seen`, `list_recent_changes`) — via the existing Mongo-mapping test
  style / fakes; assert `is_latest` transitions and `previous_version`/window
  filtering.
- **`build_version_update_message`** — formats changes + count; empty-changes
  behavior.
- **`handle_scan_versions`** — changes present → message with old→new; empty →
  "No version updates."; errors surfaced in the footer.
- **Scheduler wiring** — `_run_sync` populates `version_report`; `_run_notify`
  posts a version section only when `list_recent_changes` is non-empty (and
  nothing when empty). Follow the existing bot/scheduler test style; if there is
  no such harness yet, cover the reachable pure pieces and keep the bot glue
  thin.
- **Backward compatibility** — the new `previous_version` field defaults `None`
  and loads from old docs; existing `TargetVersion` upsert/CSV/mongo tests stay
  green.

## Out of scope

- A separate version-only schedule or `/set-version-schedule` command (folded
  into sync/notify by decision 1).
- Scanning legacy per-vendor firmware configs (decision 4).
- Announcing baseline versions on first scan (decision 2 — seed silently).
- Per-target notification channels, digests, or diffing beyond old→new strings.
- Rollback/downgrade alerting semantics beyond "version string differs".
