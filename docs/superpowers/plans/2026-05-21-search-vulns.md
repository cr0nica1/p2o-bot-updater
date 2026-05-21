# Search Vulnerabilities Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `/search-vulns` Discord slash command that returns stored vulnerabilities filtered by year and/or database collection date.

**Architecture:** Reuse the existing `ExportService.snapshot()` + `group_findings()` data path so returned vulnerabilities are formatted exactly like `/sync-cves` and daily reports. Add pure helper functions and `handle_search_vulns()` in `commands.py`, then wire the slash command in `bot.py` with multi-message pagination (10 embeds per message). No repository changes are needed.

**Tech Stack:** Python 3.10+, discord.py app_commands, existing Mongo repositories, pytest + pytest-asyncio.

---

## File Structure

**Modified files:**
- `src/updater/presentation/discord_bot/commands.py` — add date/year parsing helpers and `handle_search_vulns()`.
- `src/updater/presentation/discord_bot/bot.py` — register `/search-vulns` and send paginated embed batches.
- `tests/presentation/discord_bot/test_commands.py` — add unit tests for filtering behavior and one bot import smoke assertion already in the file remains unchanged.

No new files. No repository protocol or Mongo changes.

---

## Task 1: Add pure search filtering helpers and handler

**Files:**
- Modify: `src/updater/presentation/discord_bot/commands.py`
- Modify: `tests/presentation/discord_bot/test_commands.py`

- [ ] **Step 1: Write failing handler tests**

Append these tests to `tests/presentation/discord_bot/test_commands.py` after the existing `test_show_schedule_displays_current_times` test and before `test_bot_module_exposes_main_and_build_client` if that smoke test exists:

```python
from datetime import datetime, timezone


async def test_search_vulns_year_matches_cve_id_year():
    vuln_2024 = Vulnerability(
        advisory_id="CVE-2024-12647",
        severity="HIGH",
        description="canon bug",
        created_at=datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc),
    )
    vuln_2023 = Vulnerability(
        advisory_id="CVE-2023-9999",
        severity="LOW",
        description="old bug",
        created_at=datetime(2026, 5, 21, 11, 0, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([vuln_2024, vuln_2023]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="CVE-2024-12647"),
            TargetVulnerability(target_id="t2", target_name="Other", vulnerability_id="CVE-2023-9999"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        year=2024,
        from_date="2026-05-21",
        to_date="2026-05-21",
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert "Found 1 vulnerabilities" in result.text
    assert len(result.embeds) == 1
    assert result.embeds[0].title == "CVE-2024-12647"


async def test_search_vulns_year_matches_zdi_short_year():
    vuln = Vulnerability(
        advisory_id="ZDI-24-280",
        severity="MEDIUM",
        description="zdi bug",
        created_at=datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([vuln]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="ZDI-24-280"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        year=2024,
        from_date="2026-05-21",
        to_date="2026-05-21",
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert len(result.embeds) == 1
    assert result.embeds[0].title == "ZDI-24-280"


async def test_search_vulns_year_matches_published_date_year():
    vuln = Vulnerability(
        advisory_id="VENDOR-ABC",
        severity="HIGH",
        description="vendor advisory",
        published_date=datetime(2024, 9, 10, tzinfo=timezone.utc),
        created_at=datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([vuln]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Vendor", vulnerability_id="VENDOR-ABC"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        year=2024,
        from_date="2026-05-21",
        to_date="2026-05-21",
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert len(result.embeds) == 1
    assert result.embeds[0].title == "VENDOR-ABC"


async def test_search_vulns_filters_created_at_date_range():
    in_range = Vulnerability(
        advisory_id="CVE-2024-1111",
        created_at=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
    )
    out_of_range = Vulnerability(
        advisory_id="CVE-2024-2222",
        created_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([in_range, out_of_range]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="In", vulnerability_id="CVE-2024-1111"),
            TargetVulnerability(target_id="t2", target_name="Out", vulnerability_id="CVE-2024-2222"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        year=None,
        from_date="2026-05-19",
        to_date="2026-05-21",
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert len(result.embeds) == 1
    assert result.embeds[0].title == "CVE-2024-1111"


async def test_search_vulns_defaults_to_today_when_no_dates_given():
    today_vuln = Vulnerability(
        advisory_id="CVE-2024-1111",
        created_at=datetime(2026, 5, 21, 1, 0, tzinfo=timezone.utc),
    )
    yesterday_vuln = Vulnerability(
        advisory_id="CVE-2024-2222",
        created_at=datetime(2026, 5, 20, 23, 59, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([today_vuln, yesterday_vuln]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Today", vulnerability_id="CVE-2024-1111"),
            TargetVulnerability(target_id="t2", target_name="Yesterday", vulnerability_id="CVE-2024-2222"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        year=None,
        from_date=None,
        to_date=None,
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert len(result.embeds) == 1
    assert result.embeds[0].title == "CVE-2024-1111"
    assert "collected: 2026-05-21 to 2026-05-21" in result.text


async def test_search_vulns_applies_year_and_date_with_and_logic():
    matching = Vulnerability(
        advisory_id="CVE-2024-1111",
        created_at=datetime(2026, 5, 21, 1, 0, tzinfo=timezone.utc),
    )
    wrong_year = Vulnerability(
        advisory_id="CVE-2023-2222",
        created_at=datetime(2026, 5, 21, 1, 0, tzinfo=timezone.utc),
    )
    wrong_date = Vulnerability(
        advisory_id="CVE-2024-3333",
        created_at=datetime(2026, 5, 19, 1, 0, tzinfo=timezone.utc),
    )
    services = _services(
        vuln_repo=FakeVulnRepo([matching, wrong_year, wrong_date]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Match", vulnerability_id="CVE-2024-1111"),
            TargetVulnerability(target_id="t2", target_name="WrongYear", vulnerability_id="CVE-2023-2222"),
            TargetVulnerability(target_id="t3", target_name="WrongDate", vulnerability_id="CVE-2024-3333"),
        ]),
    )

    result = await handle_search_vulns(
        services,
        year=2024,
        from_date="2026-05-21",
        to_date="2026-05-21",
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert len(result.embeds) == 1
    assert result.embeds[0].title == "CVE-2024-1111"


async def test_search_vulns_returns_no_results_message():
    services = _services(vuln_repo=FakeVulnRepo([]), link_repo=FakeLinkRepo([]))

    result = await handle_search_vulns(
        services,
        year=2024,
        from_date="2026-05-21",
        to_date="2026-05-21",
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert result.text == "No vulnerabilities found matching the filters."
    assert result.embeds == []


async def test_search_vulns_rejects_invalid_date():
    result = await handle_search_vulns(
        _services(),
        year=None,
        from_date="2026/05/21",
        to_date=None,
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert "YYYY-MM-DD" in result.text
    assert result.ephemeral is True


async def test_search_vulns_rejects_out_of_range_year():
    result = await handle_search_vulns(
        _services(),
        year=1998,
        from_date=None,
        to_date=None,
        today=datetime(2026, 5, 21, tzinfo=timezone.utc).date(),
    )

    assert "year" in result.text.lower()
    assert result.ephemeral is True
```

Also update the import list at the top of the test file to include `handle_search_vulns`:

```python
from updater.presentation.discord_bot.commands import (
    CommandResult,
    Services,
    handle_add_target,
    handle_add_vuln,
    handle_import_targets,
    handle_list_targets,
    handle_remove_target,
    handle_search_vulns,
    handle_set_schedule,
    handle_show_schedule,
    handle_show_target,
    handle_sync_cves,
)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/presentation/discord_bot/test_commands.py -k "search_vulns" -v`
Expected: FAIL during import or collection because `handle_search_vulns` does not exist yet.

- [ ] **Step 3: Add `ephemeral` to `CommandResult`**

In `src/updater/presentation/discord_bot/commands.py`, change the dataclass to:

```python
@dataclass
class CommandResult:
    text: str = ""
    embeds: list[discord.Embed] = field(default_factory=list)
    ephemeral: bool = False
```

This lets handlers mark validation errors as ephemeral while preserving the existing default behavior for all current commands.

- [ ] **Step 4: Add imports for search helpers**

At the top of `src/updater/presentation/discord_bot/commands.py`, change:

```python
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
```

to:

```python
import asyncio
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
```

- [ ] **Step 5: Add helper constants and functions**

Add these helper definitions after the `Services` dataclass and before `handle_list_targets`:

```python
_CVE_YEAR_RE = re.compile(r"\bCVE-(\d{4})-\d{4,7}\b", re.IGNORECASE)
_ZDI_YEAR_RE = re.compile(r"\bZDI-(?:CAN-)?(\d{2,4})-\d{3,7}\b", re.IGNORECASE)


def _parse_date_filter(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("dates must use YYYY-MM-DD format") from exc


def _validate_search_year(year: int | None, today: date) -> None:
    if year is None:
        return
    if year < 1999 or year > today.year + 1:
        raise ValueError(f"year must be between 1999 and {today.year + 1}")


def _finding_years(finding: dict[str, Any], vulnerability: Vulnerability | None) -> set[int]:
    values = [finding.get("advisory_id", ""), *finding.get("aliases", [])]
    years = {int(match.group(1)) for value in values for match in _CVE_YEAR_RE.finditer(value)}
    for value in values:
        for match in _ZDI_YEAR_RE.finditer(value):
            raw_year = int(match.group(1))
            years.add(2000 + raw_year if raw_year < 100 else raw_year)
    if vulnerability is not None and vulnerability.published_date is not None:
        years.add(vulnerability.published_date.year)
    return years


def _created_date(vulnerability: Vulnerability | None) -> date | None:
    if vulnerability is None:
        return None
    created_at = vulnerability.created_at
    if created_at.tzinfo is None:
        return created_at.date()
    return created_at.astimezone(timezone.utc).date()


def _format_search_summary(
    *,
    total: int,
    year: int | None,
    from_day: date,
    to_day: date,
) -> str:
    filters: list[str] = []
    if year is not None:
        filters.append(f"year: {year}")
    filters.append(f"collected: {from_day.isoformat()} to {to_day.isoformat()}")
    return f"Found {total} vulnerabilities (" + ", ".join(filters) + ")"
```

- [ ] **Step 6: Add `handle_search_vulns`**

Add this handler immediately after `handle_sync_cves` and before `handle_set_schedule`:

```python
async def handle_search_vulns(
    services: Services,
    *,
    year: int | None,
    from_date: str | None,
    to_date: str | None,
    today: date | None = None,
) -> CommandResult:
    today = today or datetime.now(timezone.utc).date()
    try:
        _validate_search_year(year, today)
        from_day = _parse_date_filter(from_date)
        to_day = _parse_date_filter(to_date)
    except ValueError as exc:
        return CommandResult(text=str(exc), ephemeral=True)

    if from_day is None and to_day is None:
        from_day = today
        to_day = today
    elif from_day is None:
        from_day = to_day
    elif to_day is None:
        to_day = from_day

    if from_day > to_day:
        return CommandResult(text="from_date must be before or equal to to_date", ephemeral=True)

    vulnerabilities = services.vulnerability_repo.list_all()
    vulnerabilities_by_id: dict[str, Vulnerability] = {}
    for vulnerability in vulnerabilities:
        if vulnerability.id:
            vulnerabilities_by_id[vulnerability.id] = vulnerability
        vulnerabilities_by_id[vulnerability.advisory_id] = vulnerability

    snapshot = await asyncio.to_thread(
        ExportService(
            services.target_repo,
            services.vulnerability_repo,
            services.target_vulnerability_repo,
        ).snapshot
    )
    findings = group_findings(snapshot)

    filtered: list[dict[str, Any]] = []
    for finding in findings:
        vulnerability = vulnerabilities_by_id.get(finding.get("advisory_id", ""))
        created_day = _created_date(vulnerability)
        if created_day is None or created_day < from_day or created_day > to_day:
            continue
        if year is not None and year not in _finding_years(finding, vulnerability):
            continue
        filtered.append(finding)

    if not filtered:
        return CommandResult(text="No vulnerabilities found matching the filters.")

    summary = _format_search_summary(
        total=len(filtered), year=year, from_day=from_day, to_day=to_day
    )
    return CommandResult(
        text=summary,
        embeds=[build_finding_embed(finding) for finding in filtered],
    )
```

- [ ] **Step 7: Run targeted tests**

Run: `pytest tests/presentation/discord_bot/test_commands.py -k "search_vulns" -v`
Expected: 9 PASS.

- [ ] **Step 8: Run full command tests**

Run: `pytest tests/presentation/discord_bot/test_commands.py -v`
Expected: all tests PASS.

- [ ] **Step 9: Commit**

```bash
git add src/updater/presentation/discord_bot/commands.py tests/presentation/discord_bot/test_commands.py
git commit -m "feat(bot): add search_vulns handler and filters"
```

---

## Task 2: Wire `/search-vulns` slash command with pagination

**Files:**
- Modify: `src/updater/presentation/discord_bot/bot.py`
- Modify: `tests/presentation/discord_bot/test_commands.py`

- [ ] **Step 1: Add a smoke test for pagination helper**

Append this test to `tests/presentation/discord_bot/test_commands.py`:

```python
def test_chunk_embeds_splits_in_batches_of_ten():
    from updater.presentation.discord_bot.bot import _chunk_embeds

    chunks = list(_chunk_embeds([object() for _ in range(23)], size=10))

    assert [len(chunk) for chunk in chunks] == [10, 10, 3]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/presentation/discord_bot/test_commands.py::test_chunk_embeds_splits_in_batches_of_ten -v`
Expected: FAIL with `ImportError` or `AttributeError` because `_chunk_embeds` does not exist.

- [ ] **Step 3: Add `_chunk_embeds` helper**

In `src/updater/presentation/discord_bot/bot.py`, add this helper before `build_client`:

```python
def _chunk_embeds(embeds: list[object], *, size: int = 10) -> list[list[object]]:
    return [embeds[index:index + size] for index in range(0, len(embeds), size)]
```

- [ ] **Step 4: Register `/search-vulns` command**

In `build_client`, add this command after `/sync-cves` and before `/set-schedule`:

```python
    @tree.command(name="search-vulns", description="Search stored vulnerabilities", guild=guild)
    @app_commands.describe(
        year="Optional year to match by advisory ID or published date",
        from_date="Optional collected start date (YYYY-MM-DD); defaults to today",
        to_date="Optional collected end date (YYYY-MM-DD); defaults to today",
    )
    async def search_vulns(
        interaction: discord.Interaction,
        year: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ):
        await interaction.response.defer(thinking=True, ephemeral=False)
        result = await cmd.handle_search_vulns(
            services,
            year=year,
            from_date=from_date,
            to_date=to_date,
        )
        if result.ephemeral:
            await interaction.followup.send(content=result.text, ephemeral=True)
            return
        if not result.embeds:
            await interaction.followup.send(content=result.text)
            return
        chunks = _chunk_embeds(result.embeds, size=10)
        await interaction.followup.send(
            content=f"{result.text} — showing 1-{len(chunks[0])} of {len(result.embeds)}",
            embeds=chunks[0],
        )
        shown = len(chunks[0])
        for chunk in chunks[1:]:
            start = shown + 1
            shown += len(chunk)
            await interaction.followup.send(
                content=f"Showing {start}-{shown} of {len(result.embeds)}",
                embeds=chunk,
            )
```

- [ ] **Step 5: Update command count smoke assertion if present**

If any smoke test or helper in `tests/presentation/discord_bot/test_commands.py` counts commands, update expected count from 9 to 10. If no such test exists, do nothing.

- [ ] **Step 6: Run targeted test**

Run: `pytest tests/presentation/discord_bot/test_commands.py::test_chunk_embeds_splits_in_batches_of_ten -v`
Expected: PASS.

- [ ] **Step 7: Run full suite**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add src/updater/presentation/discord_bot/bot.py tests/presentation/discord_bot/test_commands.py
git commit -m "feat(bot): wire search-vulns slash command"
```

---

## Task 3: Update README command list

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add `/search-vulns` to README**

In `README.md`, find the slash command list and add this row/bullet in the read-only commands section:

```markdown
- `/search-vulns [year] [from_date] [to_date]` — search stored vulnerabilities by advisory/published year and collection date range. If no dates are supplied, defaults to vulnerabilities stored today. Dates use `YYYY-MM-DD`.
```

If the README uses a table instead of bullets, add the same command as a table row with Admin-only = `No`.

- [ ] **Step 2: Run grep to confirm README contains the command**

Run: `grep -n "search-vulns" README.md`
Expected: at least one matching line.

- [ ] **Step 3: Run tests**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document search-vulns slash command"
```

---

## Verification

After all tasks, run:

```bash
pytest -q
```

Expected: all tests PASS.

Manual Discord smoke checks after restarting `updater-bot`:

```text
/search-vulns
```

Expected: returns vulnerabilities stored today.

```text
/search-vulns year: 2024
```

Expected: returns vulnerabilities stored today whose ID/published year matches 2024.

```text
/search-vulns from_date: 2026-05-01 to_date: 2026-05-21
```

Expected: returns vulnerabilities stored in that inclusive date range.

```text
/search-vulns year: 2024 from_date: 2026-05-01 to_date: 2026-05-21
```

Expected: returns only vulnerabilities matching both year and collected date range.

```text
/search-vulns from_date: 2026/05/01
```

Expected: ephemeral error explaining `YYYY-MM-DD` format.
