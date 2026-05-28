# Sync CVEs New Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make manual `/sync-cves` and scheduled sync notifications send embeds only for vulnerabilities newly created during the sync run.

**Architecture:** Capture a sync start timestamp before running the vulnerability sync, preserve existing vulnerability `created_at` values through upserts, then filter grouped notification findings against vulnerability records with `created_at >= sync_started_at`. Manual `/sync-cves` already has this shape; scheduled sync/notify needs the same data flow instead of notifying the full database snapshot.

**Tech Stack:** Python 3.11+, `discord.py`, pytest/pytest-asyncio, Mongo-style repository protocols, existing `ExportService` and Discord formatting helpers.

---

## File Structure

- `src/updater/presentation/discord_bot/commands.py`
  - Keep the manual `/sync-cves` filtering behavior.
  - Extract the filtering logic into a small helper so scheduled notify and manual sync use the same rule.
- `src/updater/presentation/discord_bot/bot.py`
  - Change scheduled `_run_sync` to return sync metadata, including `sync_started_at` and the sync result.
  - Pass `sync_started_at` into `_run_notify` and filter scheduled findings before sending embeds.
- `tests/presentation/discord_bot/test_commands.py`
  - Add or adjust tests for the shared filtering helper and scheduled notify behavior.

No database schema change is needed because `Vulnerability.created_at` already exists and `MongoVulnerabilityRepository.upsert()` already preserves `created_at` for existing rows.

---

### Task 1: Extract New-Findings Filtering Helper

**Files:**
- Modify: `src/updater/presentation/discord_bot/commands.py:61-72`
- Modify: `src/updater/presentation/discord_bot/commands.py:357-396`
- Test: `tests/presentation/discord_bot/test_commands.py`

- [ ] **Step 1: Write the failing helper test**

Append this test near the existing `/sync-cves` tests in `tests/presentation/discord_bot/test_commands.py`:

```python
def test_filter_findings_to_created_since_keeps_only_new_vulnerabilities():
    from updater.presentation.discord_bot.commands import filter_findings_to_created_since

    sync_started_at = datetime(2026, 5, 21, 13, 34, 0, tzinfo=timezone.utc)
    old = Vulnerability(
        advisory_id="CVE-2024-0001",
        created_at=datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc),
    )
    fresh = Vulnerability(
        advisory_id="CVE-2024-0002",
        created_at=datetime(2026, 5, 21, 13, 34, 30, tzinfo=timezone.utc),
    )
    findings = [
        {"advisory_id": "CVE-2024-0001", "target_names": ["Canon"]},
        {"advisory_id": "CVE-2024-0002", "target_names": ["Canon"]},
    ]

    filtered = filter_findings_to_created_since(
        findings,
        [old, fresh],
        sync_started_at,
    )

    assert [finding["advisory_id"] for finding in filtered] == ["CVE-2024-0002"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_filter_findings_to_created_since_keeps_only_new_vulnerabilities -v
```

Expected: FAIL with an import error because `filter_findings_to_created_since` does not exist yet.

- [ ] **Step 3: Add the shared helper**

In `src/updater/presentation/discord_bot/commands.py`, after `_vulnerability_lookup`, add:

```python
def filter_findings_to_created_since(
    findings: list[dict[str, Any]],
    vulnerabilities: list[Vulnerability],
    sync_started_at: datetime,
) -> list[dict[str, Any]]:
    vulnerabilities_by_id = _vulnerability_lookup(vulnerabilities)
    return [
        finding
        for finding in findings
        if (vulnerability := vulnerabilities_by_id.get(finding.get("advisory_id", ""))) is not None
        and vulnerability.created_at >= sync_started_at
    ]
```

- [ ] **Step 4: Update manual `/sync-cves` to use the helper**

In `handle_sync_cves()` in `src/updater/presentation/discord_bot/commands.py`, replace:

```python
    vulnerabilities_by_id = _vulnerability_lookup(await asyncio.to_thread(services.vulnerability_repo.list_all))
```

with:

```python
    vulnerabilities = await asyncio.to_thread(services.vulnerability_repo.list_all)
```

Then replace the final filtering block:

```python
    findings = [
        finding
        for finding in findings
        if (vulnerability := vulnerabilities_by_id.get(finding.get("advisory_id", ""))) is not None
        and vulnerability.created_at >= sync_started_at
    ]
```

with:

```python
    findings = filter_findings_to_created_since(findings, vulnerabilities, sync_started_at)
```

- [ ] **Step 5: Run helper and existing manual sync tests**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_filter_findings_to_created_since_keeps_only_new_vulnerabilities tests/presentation/discord_bot/test_commands.py::test_sync_cves_only_reports_vulnerabilities_stored_since_sync_minute tests/presentation/discord_bot/test_commands.py::test_sync_cves_returns_embeds_for_findings -v
```

Expected: PASS.

---

### Task 2: Filter Scheduled Notifications by Sync Start Time

**Files:**
- Modify: `src/updater/presentation/discord_bot/bot.py:318-343`
- Modify: `src/updater/presentation/discord_bot/bot.py:367-418`
- Test: `tests/presentation/discord_bot/test_commands.py`

- [ ] **Step 1: Write the failing scheduled notify test**

Append this test near the existing bot helper tests in `tests/presentation/discord_bot/test_commands.py`:

```python
async def test_run_notify_only_sends_vulnerabilities_created_since_sync_start():
    from updater.presentation.discord_bot.bot import _run_notify

    old = Vulnerability(
        id="old-vuln",
        advisory_id="CVE-2024-0001",
        severity="LOW",
        description="old bug already in db",
        created_at=datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc),
    )
    fresh = Vulnerability(
        id="fresh-vuln",
        advisory_id="CVE-2024-0002",
        severity="HIGH",
        description="new bug from this sync",
        created_at=datetime(2026, 5, 21, 13, 34, 30, tzinfo=timezone.utc),
    )
    target = Target(id="t1", name="Canon")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vuln_repo=FakeVulnRepo([old, fresh]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="old-vuln"),
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="fresh-vuln"),
        ]),
    )
    sent = []

    class FakeChannel:
        async def send(self, **kwargs):
            sent.append(kwargs)

    await _run_notify(
        services,
        FakeChannel(),
        timezone.utc,
        sync_started_at=datetime(2026, 5, 21, 13, 34, 0, tzinfo=timezone.utc),
    )

    assert sent[0]["content"] == (
        "Daily Vulnerability Report — 2026-05-21\n"
        "Targets processed: 1\n"
        "New findings: 1\n"
        "Errors: 0"
    )
    assert len(sent) == 2
    assert sent[1]["embed"].title == "CVE-2024-0002"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_run_notify_only_sends_vulnerabilities_created_since_sync_start -v
```

Expected: FAIL because `_run_notify()` does not accept `sync_started_at` yet.

- [ ] **Step 3: Import the shared helper in `bot.py`**

In `src/updater/presentation/discord_bot/bot.py`, update the formatting/helper import area so `bot.py` can call the helper through the existing `cmd` module. No new import is necessary because `cmd` is already imported as:

```python
from updater.presentation.discord_bot import commands as cmd
```

Use `cmd.filter_findings_to_created_since(...)` in the implementation step.

- [ ] **Step 4: Update `_run_notify()` signature and filtering**

Replace the `_run_notify` definition and its first finding-processing lines in `src/updater/presentation/discord_bot/bot.py` with this shape:

```python
async def _run_notify(services: cmd.Services, channel, tz, *, sync_started_at: datetime | None = None) -> None:
    log.info("scheduled notify starting")
    try:
        vulnerabilities = await asyncio.to_thread(services.vulnerability_repo.list_all)
        snapshot = await asyncio.to_thread(
            ExportService(
                services.target_repo,
                services.vulnerability_repo,
                services.target_vulnerability_repo,
            ).snapshot
        )
    except Exception:
        log.exception("scheduled notify failed (snapshot)")
        return

    findings = group_findings(snapshot)
    if sync_started_at is not None:
        findings = cmd.filter_findings_to_created_since(findings, vulnerabilities, sync_started_at)
```

Keep the existing summary/send loop after this block unchanged, so `new_findings=len(findings)` reflects the filtered count.

- [ ] **Step 5: Run the scheduled notify test**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_run_notify_only_sends_vulnerabilities_created_since_sync_start -v
```

Expected: PASS.

---

### Task 3: Wire Scheduled Sync Timestamp into Scheduler

**Files:**
- Modify: `src/updater/presentation/discord_bot/bot.py:318-343`
- Modify: `src/updater/presentation/discord_bot/bot.py:367-385`
- Test: `tests/presentation/discord_bot/test_commands.py`

- [ ] **Step 1: Write a focused unit test for `_run_sync()` metadata**

Append this test near the scheduled notify test in `tests/presentation/discord_bot/test_commands.py`:

```python
async def test_run_sync_returns_sync_start_timestamp():
    from unittest.mock import patch

    from updater.presentation.discord_bot.bot import _run_sync

    target = Target(id="t1", name="Canon")
    services = _services(target_repo=FakeTargetRepo([target]), sources=[])
    sync_start = datetime(2026, 5, 21, 13, 34, 30, tzinfo=timezone.utc)

    with patch("updater.presentation.discord_bot.bot.datetime") as mock_dt:
        mock_dt.now.return_value = sync_start
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = await _run_sync(services)

    assert result is not None
    assert result.sync_started_at == sync_start
    assert result.sync_result.targets_processed == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_run_sync_returns_sync_start_timestamp -v
```

Expected: FAIL because `_run_sync()` currently returns `None`.

- [ ] **Step 3: Add a scheduled sync metadata dataclass**

In `src/updater/presentation/discord_bot/bot.py`, add this import near the top:

```python
from dataclasses import dataclass
```

Then add this dataclass after `_resolve_channel()`:

```python
@dataclass
class ScheduledSyncRun:
    sync_started_at: datetime
    sync_result: object
```

- [ ] **Step 4: Update `_run_sync()` to return metadata**

Replace `_run_sync()` in `src/updater/presentation/discord_bot/bot.py` with:

```python
async def _run_sync(services: cmd.Services) -> ScheduledSyncRun | None:
    log.info("scheduled sync starting")
    sync_started_at = datetime.now(timezone.utc)
    try:
        result = await asyncio.to_thread(
            SyncVulnerabilitiesService(
                services.target_repo,
                services.vulnerability_repo,
                services.target_vulnerability_repo,
                services.sources,
            ).sync_all
        )
        log.info(
            "scheduled sync done targets=%d vulns=%d errors=%d",
            result.targets_processed,
            result.vulnerabilities_seen,
            len(result.errors),
        )
        return ScheduledSyncRun(sync_started_at=sync_started_at, sync_result=result)
    except Exception:
        log.exception("scheduled sync failed")
        return None
```

- [ ] **Step 5: Thread the sync metadata through the scheduler loop**

In `_scheduler_loop()` in `src/updater/presentation/discord_bot/bot.py`, before `for event in events:`, add:

```python
                sync_run = None
```

Then replace:

```python
                if event == "sync":
                    await _run_sync(services)
```

with:

```python
                if event == "sync":
                    sync_run = await _run_sync(services)
```

Finally replace:

```python
                    await _run_notify(services, channel, current.tz)
```

with:

```python
                    await _run_notify(
                        services,
                        channel,
                        current.tz,
                        sync_started_at=sync_run.sync_started_at if sync_run is not None else None,
                    )
```

This means when the scheduler fires both `sync` and `notify` in the same tick, notify filters to vulnerabilities created during that just-finished sync. If notify fires separately without a same-tick sync, it keeps the existing behavior because there is no sync timestamp for that tick.

- [ ] **Step 6: Run sync metadata and notify tests**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_run_sync_returns_sync_start_timestamp tests/presentation/discord_bot/test_commands.py::test_run_notify_only_sends_vulnerabilities_created_since_sync_start -v
```

Expected: PASS.

---

### Task 4: Final Verification

**Files:**
- Test only: no source changes expected.

- [ ] **Step 1: Run targeted Discord bot tests**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py tests/presentation/discord_bot/test_scheduler.py tests/presentation/discord_bot/test_formatting.py -v
```

Expected: PASS.

- [ ] **Step 2: Run sync service tests**

Run:

```bash
pytest tests/application/test_sync_vulnerabilities.py -v
```

Expected: PASS.

- [ ] **Step 3: Run the full test suite**

Run:

```bash
pytest -q
```

Expected: PASS.

- [ ] **Step 4: Inspect changed files**

Run:

```bash
git diff -- src/updater/presentation/discord_bot/commands.py src/updater/presentation/discord_bot/bot.py tests/presentation/discord_bot/test_commands.py
```

Expected: Diff contains only the shared created-at filtering helper, scheduled sync timestamp plumbing, scheduled notify filtering, and tests.

---

## Self-Review

- Spec coverage: Manual `/sync-cves` and scheduled notify both use `created_at >= sync_started_at`; no database migration is needed; no notification is sent for old database vulnerabilities when a sync timestamp is available.
- Placeholder scan: No TBD/TODO/fill-in placeholders remain.
- Type consistency: `filter_findings_to_created_since()` accepts grouped findings, `list[Vulnerability]`, and `datetime`; `_run_notify()` accepts optional `sync_started_at`; `_run_sync()` returns `ScheduledSyncRun | None`.
