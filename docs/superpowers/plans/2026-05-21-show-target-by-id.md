# Show Target By ID Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update Discord `/list-targets` and `/show-target` so users choose a target by numbered display ID and can view recent vulnerabilities for that target.

**Architecture:** Keep the behavior in `updater.presentation.discord_bot.commands`, where command handlers already translate repositories into `CommandResult`. Use the same alphabetically sorted target list for both `/list-targets` and `/show-target`, and build vulnerability embeds directly from repository models so sorting can use `published_date` and `created_at`.

**Tech Stack:** Python 3.10+, discord.py command handlers, pytest + pytest-asyncio.

---

## File Structure

- Modify `src/updater/presentation/discord_bot/commands.py`
  - Add small helpers for sorted target display IDs, target ID resolution, vulnerability sorting, and finding dict construction.
  - Change `handle_list_targets()` to number sorted targets.
  - Change `handle_show_target()` to accept `target_id: int` and `limit: int | None`.
- Modify `src/updater/presentation/discord_bot/bot.py`
  - Change slash command parameters from `name` to `target_id` and `limit`.
- Modify `tests/presentation/discord_bot/test_commands.py`
  - Update list-targets and show-target tests.
  - Add coverage for invalid target IDs and limiting recent vulnerabilities.

---

### Task 1: Number `/list-targets` output alphabetically

**Files:**
- Modify: `tests/presentation/discord_bot/test_commands.py`
- Modify: `src/updater/presentation/discord_bot/commands.py`

- [ ] **Step 1: Write the failing test**

Replace the existing `test_list_targets_returns_names` test in `tests/presentation/discord_bot/test_commands.py` with:

```python
async def test_list_targets_returns_numbered_names_sorted_alphabetically():
    services = _services(target_repo=FakeTargetRepo([
        Target(id="t2", name="Canon MF654Cdw"),
        Target(id="t1", name="Adobe Reader"),
    ]))

    result = await handle_list_targets(services)

    assert result.text == "Targets:\n1. Adobe Reader\n2. Canon MF654Cdw"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/presentation/discord_bot/test_commands.py::test_list_targets_returns_numbered_names_sorted_alphabetically -q
```

Expected: FAIL because current output uses `- name` and preserves repository order.

- [ ] **Step 3: Write minimal implementation**

In `src/updater/presentation/discord_bot/commands.py`, add this helper after `UTC_PLUS_7 = timezone(timedelta(hours=7))`:

```python
def _sorted_targets(services: Services) -> list[Target]:
    return sorted(services.target_repo.list_all(), key=lambda target: target.name.casefold())
```

Replace `handle_list_targets()` with:

```python
async def handle_list_targets(services: Services) -> CommandResult:
    targets = _sorted_targets(services)
    if not targets:
        return CommandResult(text="No targets configured.")
    lines = [f"{index}. {target.name}" for index, target in enumerate(targets, start=1)]
    return CommandResult(text="Targets:\n" + "\n".join(lines))
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/presentation/discord_bot/test_commands.py::test_list_targets_returns_numbered_names_sorted_alphabetically -q
```

Expected: PASS.

---

### Task 2: Resolve `/show-target` by numbered target ID

**Files:**
- Modify: `tests/presentation/discord_bot/test_commands.py`
- Modify: `src/updater/presentation/discord_bot/commands.py`

- [ ] **Step 1: Write the failing tests**

Replace the existing `test_show_target_includes_vulnerability_count` with:

```python
async def test_show_target_resolves_numbered_target_id_from_sorted_list():
    target = Target(id="t1", name="Adobe Reader", aliases=["Acrobat"], vendor="Adobe", category="pdf")
    services = _services(target_repo=FakeTargetRepo([
        Target(id="t2", name="Canon MF654Cdw"),
        target,
    ]))

    result = await handle_show_target(services, target_id=1, limit=None)

    assert result.text.splitlines()[:5] == [
        "Target #1: Adobe Reader",
        "Aliases: Acrobat",
        "Vendor: Adobe",
        "Category: pdf",
        "No vulnerabilities found.",
    ]
    assert result.embeds == []
```

Replace the existing `test_show_target_not_found` with:

```python
async def test_show_target_rejects_out_of_range_target_id():
    services = _services(target_repo=FakeTargetRepo([Target(id="t1", name="Adobe Reader")]))

    result = await handle_show_target(services, target_id=2, limit=None)

    assert result.text == "Invalid target ID. Use /list-targets to see available targets (1-1)."
    assert result.ephemeral is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/presentation/discord_bot/test_commands.py::test_show_target_resolves_numbered_target_id_from_sorted_list tests/presentation/discord_bot/test_commands.py::test_show_target_rejects_out_of_range_target_id -q
```

Expected: FAIL because `handle_show_target()` still requires `name`.

- [ ] **Step 3: Write minimal implementation**

In `src/updater/presentation/discord_bot/commands.py`, add this helper after `_sorted_targets()`:

```python
def _target_storage_id(target: Target) -> str:
    return target.id or target.normalized_name
```

Replace `handle_show_target()` with:

```python
async def handle_show_target(services: Services, *, target_id: int, limit: int | None) -> CommandResult:
    targets = _sorted_targets(services)
    if target_id < 1 or target_id > len(targets):
        return CommandResult(
            text=f"Invalid target ID. Use /list-targets to see available targets (1-{len(targets)}).",
            ephemeral=True,
        )

    target = targets[target_id - 1]
    lines = [
        f"Target #{target_id}: {target.name}",
        f"Aliases: {', '.join(target.aliases) or '—'}",
        f"Vendor: {target.vendor or '—'}",
        f"Category: {target.category or '—'}",
        "No vulnerabilities found.",
    ]
    return CommandResult(text="\n".join(lines))
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/presentation/discord_bot/test_commands.py::test_show_target_resolves_numbered_target_id_from_sorted_list tests/presentation/discord_bot/test_commands.py::test_show_target_rejects_out_of_range_target_id -q
```

Expected: PASS.

---

### Task 3: Display target vulnerabilities sorted by recency

**Files:**
- Modify: `tests/presentation/discord_bot/test_commands.py`
- Modify: `src/updater/presentation/discord_bot/commands.py`

- [ ] **Step 1: Write the failing test**

Add this test near the other show-target tests in `tests/presentation/discord_bot/test_commands.py`:

```python
async def test_show_target_returns_vulnerability_embeds_sorted_by_recent_date():
    old = Vulnerability(
        id="v-old",
        advisory_id="CVE-2024-0001",
        severity="LOW",
        description="old bug",
        published_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    new = Vulnerability(
        id="v-new",
        advisory_id="CVE-2024-0002",
        severity="HIGH",
        description="new bug",
        published_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
    )
    target = Target(id="t1", name="Canon")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vuln_repo=FakeVulnRepo([old, new]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="v-old"),
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="v-new"),
        ]),
    )

    result = await handle_show_target(services, target_id=1, limit=None)

    assert "Showing 2 of 2 vulnerabilities" in result.text
    assert [embed.title for embed in result.embeds] == ["CVE-2024-0002", "CVE-2024-0001"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/presentation/discord_bot/test_commands.py::test_show_target_returns_vulnerability_embeds_sorted_by_recent_date -q
```

Expected: FAIL because `handle_show_target()` does not build embeds yet.

- [ ] **Step 3: Write minimal implementation**

In `src/updater/presentation/discord_bot/commands.py`, add these helpers after `_target_storage_id()`:

```python
def _vulnerability_lookup(vulnerabilities: list[Vulnerability]) -> dict[str, Vulnerability]:
    lookup: dict[str, Vulnerability] = {}
    for vulnerability in vulnerabilities:
        if vulnerability.id:
            lookup[vulnerability.id] = vulnerability
        lookup[vulnerability.advisory_id] = vulnerability
    return lookup


def _vulnerability_sort_time(vulnerability: Vulnerability) -> datetime:
    return vulnerability.published_date or vulnerability.created_at


def _finding_for_target(vulnerability: Vulnerability, target: Target) -> dict[str, Any]:
    return {
        "advisory_id": vulnerability.advisory_id,
        "aliases": list(vulnerability.aliases),
        "cvss_score": vulnerability.cvss_score,
        "severity": vulnerability.severity,
        "description": vulnerability.description or "",
        "references": list(vulnerability.references),
        "target_names": [target.name],
    }
```

Update `handle_show_target()` to:

```python
async def handle_show_target(services: Services, *, target_id: int, limit: int | None) -> CommandResult:
    targets = _sorted_targets(services)
    if target_id < 1 or target_id > len(targets):
        return CommandResult(
            text=f"Invalid target ID. Use /list-targets to see available targets (1-{len(targets)}).",
            ephemeral=True,
        )

    target = targets[target_id - 1]
    storage_id = _target_storage_id(target)
    links = [
        link
        for link in services.target_vulnerability_repo.list_all()
        if link.target_id == storage_id
    ]
    vulnerabilities_by_id = _vulnerability_lookup(services.vulnerability_repo.list_all())
    vulnerabilities = [
        vulnerabilities_by_id[link.vulnerability_id]
        for link in links
        if link.vulnerability_id in vulnerabilities_by_id
    ]
    vulnerabilities.sort(key=_vulnerability_sort_time, reverse=True)

    total = len(vulnerabilities)
    if limit is not None and limit > 0:
        vulnerabilities = vulnerabilities[:limit]

    lines = [
        f"Target #{target_id}: {target.name}",
        f"Aliases: {', '.join(target.aliases) or '—'}",
        f"Vendor: {target.vendor or '—'}",
        f"Category: {target.category or '—'}",
    ]
    if total == 0:
        lines.append("No vulnerabilities found.")
    else:
        lines.append(f"Showing {len(vulnerabilities)} of {total} vulnerabilities")

    embeds = [build_finding_embed(_finding_for_target(vulnerability, target)) for vulnerability in vulnerabilities]
    return CommandResult(text="\n".join(lines), embeds=embeds)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/presentation/discord_bot/test_commands.py::test_show_target_returns_vulnerability_embeds_sorted_by_recent_date -q
```

Expected: PASS.

---

### Task 4: Apply `limit` to recent vulnerabilities

**Files:**
- Modify: `tests/presentation/discord_bot/test_commands.py`
- Modify: `src/updater/presentation/discord_bot/commands.py`

- [ ] **Step 1: Write the failing test**

Add this test near the previous show-target vulnerability test:

```python
async def test_show_target_limit_shows_only_most_recent_vulnerabilities():
    target = Target(id="t1", name="Canon")
    newest = Vulnerability(
        id="v-newest",
        advisory_id="CVE-2024-0003",
        created_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
    )
    middle = Vulnerability(
        id="v-middle",
        advisory_id="CVE-2024-0002",
        created_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
    )
    oldest = Vulnerability(
        id="v-oldest",
        advisory_id="CVE-2024-0001",
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vuln_repo=FakeVulnRepo([oldest, newest, middle]),
        link_repo=FakeLinkRepo([
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="v-oldest"),
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="v-newest"),
            TargetVulnerability(target_id="t1", target_name="Canon", vulnerability_id="v-middle"),
        ]),
    )

    result = await handle_show_target(services, target_id=1, limit=2)

    assert "Showing 2 of 3 vulnerabilities" in result.text
    assert [embed.title for embed in result.embeds] == ["CVE-2024-0003", "CVE-2024-0002"]
```

- [ ] **Step 2: Run test to verify behavior**

Run:

```bash
python -m pytest tests/presentation/discord_bot/test_commands.py::test_show_target_limit_shows_only_most_recent_vulnerabilities -q
```

Expected: PASS if Task 3 implementation already handles `limit`; if it fails, adjust only the limit block in `handle_show_target()` to match the Task 3 code.

---

### Task 5: Update Discord slash command signature

**Files:**
- Modify: `src/updater/presentation/discord_bot/bot.py`
- Modify: `tests/presentation/discord_bot/test_commands.py`

- [ ] **Step 1: Write the failing test**

The existing module smoke test only checks that `build_client` is callable. Add this more specific test near `test_bot_module_exposes_main_and_build_client`:

```python
def test_show_target_command_uses_target_id_and_limit_options(tmp_path):
    from pathlib import Path
    from unittest.mock import patch

    from updater.presentation.discord_bot.bot import build_client
    from updater.presentation.discord_bot.config import BotConfig, UTC_PLUS_7

    config = BotConfig(
        env_path=Path(tmp_path / ".env"),
        discord_token="token",
        guild_id=1,
        channel_id=2,
        admin_role_id=3,
        sync_time=(8, 0),
        notify_time=(9, 0),
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="test",
        tz=UTC_PLUS_7,
    )

    with patch("updater.presentation.discord_bot.bot._build_services", return_value=_services()):
        client = build_client(config)

    show_target = next(command for command in client._command_tree.get_commands() if command.name == "show-target")

    assert [parameter.name for parameter in show_target.parameters] == ["target_id", "limit"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/presentation/discord_bot/test_commands.py::test_show_target_command_uses_target_id_and_limit_options -q
```

Expected: FAIL because the command still has `name` only.

- [ ] **Step 3: Update command signature**

In `src/updater/presentation/discord_bot/bot.py`, replace the `show-target` command block with:

```python
    @tree.command(name="show-target", description="Show target details", guild=guild)
    @app_commands.describe(
        target_id="Target number from /list-targets",
        limit="Optional number of recent vulnerabilities to show",
    )
    async def show_target(
        interaction: discord.Interaction,
        target_id: int,
        limit: int | None = None,
    ):
        await _reply(interaction, await cmd.handle_show_target(services, target_id=target_id, limit=limit))
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/presentation/discord_bot/test_commands.py::test_show_target_command_uses_target_id_and_limit_options -q
```

Expected: PASS.

---

### Task 6: Run focused and full verification

**Files:**
- Verify only; no code changes expected.

- [ ] **Step 1: Run all Discord command tests**

Run:

```bash
python -m pytest tests/presentation/discord_bot/test_commands.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run full test suite**

Run:

```bash
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Inspect diff**

Run:

```bash
git diff -- src/updater/presentation/discord_bot/commands.py src/updater/presentation/discord_bot/bot.py tests/presentation/discord_bot/test_commands.py
```

Expected: diff only contains the numbered list-targets behavior, show-target ID/limit behavior, slash command signature update, and tests.

---

## Self-Review

- Spec coverage: `/list-targets` numbering is covered in Task 1. `/show-target target_id` and invalid IDs are covered in Task 2. Vulnerability details are covered in Task 3. Optional recent limit is covered in Task 4. Discord slash command options are covered in Task 5. Full verification is covered in Task 6.
- Placeholder scan: no TBD/TODO/fill-in steps remain.
- Type consistency: `handle_show_target(services, *, target_id: int, limit: int | None)` is used consistently in tests and bot command wiring.
