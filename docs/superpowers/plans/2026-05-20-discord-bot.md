# Discord Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `updater` CLI with a Discord bot that exposes the same functionality through slash commands, adds a daily sync + notification scheduler, and supports manual vulnerability entry.

**Architecture:** A new `presentation/discord_bot/` package wraps existing application services and MongoDB repositories. Slash commands are handled via `discord.py`'s `app_commands`. A `discord.ext.tasks` loop checks every 60 seconds whether the configured `SYNC_TIME` or `NOTIFY_TIME` has elapsed for the current day and triggers the corresponding action. Configuration lives in `.env`; `/set-schedule` rewrites the file in place. Domain/application layers are unchanged except for two small repository additions (`delete(name)`, `delete_by_target(target_id)`).

**Tech Stack:** Python 3.10+, `discord.py>=2.3.0`, `python-dotenv>=1.0.0`, `pymongo`, `pytest`, `pytest-asyncio`.

---

## File Structure

**New files:**
- `src/updater/presentation/discord_bot/__init__.py` — package marker
- `src/updater/presentation/discord_bot/config.py` — `.env` load/validate/rewrite
- `src/updater/presentation/discord_bot/permissions.py` — admin role check
- `src/updater/presentation/discord_bot/formatting.py` — embed + summary builders
- `src/updater/presentation/discord_bot/scheduler.py` — pure "should fire" tracker
- `src/updater/presentation/discord_bot/commands.py` — pure async handlers (no discord types in signatures except `discord.Embed`)
- `src/updater/presentation/discord_bot/bot.py` — discord client, command tree, scheduler loop, entrypoint
- `tests/presentation/discord_bot/__init__.py`
- `tests/presentation/discord_bot/test_config.py`
- `tests/presentation/discord_bot/test_permissions.py`
- `tests/presentation/discord_bot/test_formatting.py`
- `tests/presentation/discord_bot/test_scheduler.py`
- `tests/presentation/discord_bot/test_commands.py`

**Modified files:**
- `pyproject.toml` — add `discord.py`, `python-dotenv`, `pytest-asyncio`; replace `updater` script with `updater-bot`.
- `src/updater/__main__.py` — point to bot entrypoint
- `src/updater/domain/repositories.py` — add `delete(name)` to `TargetRepository` and `delete_by_target(target_id)` to `TargetVulnerabilityRepository`
- `src/updater/infrastructure/mongo.py` — implement those two delete methods
- `tests/infrastructure/test_mongo_mapping.py` — cover the new delete methods

**Deleted files:**
- `src/updater/presentation/cli.py`
- `tests/presentation/test_cli.py`

---

## Task 1: Add dependencies and pytest-asyncio config

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the new dependencies and pytest-asyncio mode**

Replace the `[project]` `dependencies` array and the existing `[project.scripts]` block, and add `[tool.pytest.ini_options]` `asyncio_mode`:

```toml
[project]
name = "pwn2own-updater"
version = "0.1.0"
description = "Discord bot for tracking Pwn2Own target vulnerabilities"
requires-python = ">=3.10"
dependencies = [
    "beautifulsoup4>=4.12.0",
    "discord.py>=2.3.0",
    "pymongo>=4.6.0",
    "python-dotenv>=1.0.0",
    "requests>=2.31.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]

[project.scripts]
updater-bot = "updater.presentation.discord_bot.bot:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Reinstall the package so the new entrypoint and deps land**

Run: `pip install -e ".[dev]"`
Expected: ends with `Successfully installed ... discord.py-2.x ... python-dotenv-1.x ... pytest-asyncio-0.23.x ...`

- [ ] **Step 3: Verify the imports work**

Run: `python -c "import discord, dotenv, pytest_asyncio; print(discord.__version__)"`
Expected: prints a version string `2.x.y` and exits 0.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add discord.py and python-dotenv deps, switch entrypoint"
```

---

## Task 2: Extend repository protocols with `delete` and `delete_by_target`

**Files:**
- Modify: `src/updater/domain/repositories.py`

- [ ] **Step 1: Update the `TargetRepository` and `TargetVulnerabilityRepository` Protocols**

Replace the bodies of both Protocols so they read exactly:

```python
class TargetRepository(Protocol):
    def upsert(self, target: Target) -> Target: ...
    def list_all(self) -> list[Target]: ...
    def find_by_name(self, name: str) -> Target | None: ...
    def delete(self, name: str) -> bool: ...


class TargetVulnerabilityRepository(Protocol):
    def upsert(self, link: TargetVulnerability) -> TargetVulnerability: ...
    def list_all(self) -> list[TargetVulnerability]: ...
    def delete_by_target(self, target_id: str) -> int: ...
```

- [ ] **Step 2: Run the test suite to confirm nothing breaks yet**

Run: `pytest -q`
Expected: PASS (Protocols are structural — the existing fake repositories satisfy the new methods only after Task 3, but the suite should still pass because nothing yet *calls* the new methods. If any test fails because a `cast(..., TargetRepository)` exists, fix the corresponding fake.)

- [ ] **Step 3: Commit**

```bash
git add src/updater/domain/repositories.py
git commit -m "feat(domain): add delete and delete_by_target to repository protocols"
```

---

## Task 3: Implement Mongo `delete(name)` and `delete_by_target(target_id)`

**Files:**
- Modify: `src/updater/infrastructure/mongo.py`
- Modify: `tests/infrastructure/test_mongo_mapping.py`

- [ ] **Step 1: Write the failing test for `MongoTargetRepository.delete`**

Append to `tests/infrastructure/test_mongo_mapping.py`:

```python
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
```

- [ ] **Step 2: Run the new tests; confirm they fail**

Run: `pytest tests/infrastructure/test_mongo_mapping.py -k "delete" -v`
Expected: 3 FAILs with `AttributeError: 'MongoTargetRepository' object has no attribute 'delete'` (or similar).

- [ ] **Step 3: Implement `delete` on `MongoTargetRepository`**

In `src/updater/infrastructure/mongo.py`, add this method to `MongoTargetRepository` (immediately after `delete_all`):

```python
    def delete(self, name: str) -> bool:
        result = self.collection.delete_one({"normalized_name": normalize_name(name)})
        return result.deleted_count > 0
```

- [ ] **Step 4: Implement `delete_by_target` on `MongoTargetVulnerabilityRepository`**

Add this method to `MongoTargetVulnerabilityRepository` (immediately after `delete_all`):

```python
    def delete_by_target(self, target_id: str) -> int:
        return self.collection.delete_many({"target_id": target_id}).deleted_count
```

- [ ] **Step 5: Re-run the new tests; confirm they pass**

Run: `pytest tests/infrastructure/test_mongo_mapping.py -k "delete" -v`
Expected: 3 PASS.

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/updater/infrastructure/mongo.py tests/infrastructure/test_mongo_mapping.py
git commit -m "feat(mongo): add target delete and target_vulnerability delete_by_target"
```

---

## Task 4: Discord bot package skeleton

**Files:**
- Create: `src/updater/presentation/discord_bot/__init__.py`
- Create: `tests/presentation/discord_bot/__init__.py`

- [ ] **Step 1: Create the package marker (source)**

`src/updater/presentation/discord_bot/__init__.py`:

```python
```

(Empty file.)

- [ ] **Step 2: Create the package marker (tests)**

`tests/presentation/discord_bot/__init__.py`:

```python
```

(Empty file.)

- [ ] **Step 3: Verify pytest still collects fine**

Run: `pytest -q`
Expected: all PASS, same count as before.

- [ ] **Step 4: Commit**

```bash
git add src/updater/presentation/discord_bot/__init__.py tests/presentation/discord_bot/__init__.py
git commit -m "feat(bot): add discord_bot package skeleton"
```

---

## Task 5: Config loader (parse + validate + rewrite)

**Files:**
- Create: `src/updater/presentation/discord_bot/config.py`
- Create: `tests/presentation/discord_bot/test_config.py`

- [ ] **Step 1: Write the failing tests**

`tests/presentation/discord_bot/test_config.py`:

```python
import pytest

from updater.presentation.discord_bot.config import (
    BotConfig,
    ConfigError,
    load_config,
    parse_time,
    update_schedule,
)


def test_parse_time_accepts_hh_mm():
    assert parse_time("08:00") == (8, 0)
    assert parse_time("23:59") == (23, 59)
    assert parse_time(" 9:05 ") == (9, 5)


def test_parse_time_rejects_invalid():
    with pytest.raises(ConfigError):
        parse_time("24:00")
    with pytest.raises(ConfigError):
        parse_time("8")
    with pytest.raises(ConfigError):
        parse_time("abc")
    with pytest.raises(ConfigError):
        parse_time("12:60")


def test_load_config_reads_all_fields(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=tok\n"
        "DISCORD_GUILD_ID=111\n"
        "DISCORD_CHANNEL_ID=222\n"
        "DISCORD_ADMIN_ROLE_ID=333\n"
        "SYNC_TIME=08:00\n"
        "NOTIFY_TIME=09:30\n"
        "MONGODB_URI=mongodb://localhost:27017\n"
        "MONGODB_DATABASE=pwn2own_updater\n"
    )

    config = load_config(env_file)

    assert config == BotConfig(
        env_path=env_file,
        discord_token="tok",
        guild_id=111,
        channel_id=222,
        admin_role_id=333,
        sync_time=(8, 0),
        notify_time=(9, 30),
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="pwn2own_updater",
    )


def test_load_config_missing_token_raises(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_GUILD_ID=111\n")
    with pytest.raises(ConfigError, match="DISCORD_TOKEN"):
        load_config(env_file)


def test_load_config_bad_time_raises(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=tok\n"
        "DISCORD_GUILD_ID=111\n"
        "DISCORD_CHANNEL_ID=222\n"
        "DISCORD_ADMIN_ROLE_ID=333\n"
        "SYNC_TIME=2500\n"
        "NOTIFY_TIME=09:30\n"
    )
    with pytest.raises(ConfigError, match="SYNC_TIME"):
        load_config(env_file)


def test_update_schedule_rewrites_existing_lines(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=tok\n"
        "SYNC_TIME=08:00\n"
        "NOTIFY_TIME=09:00\n"
    )

    update_schedule(env_file, sync_time="10:15", notify_time="11:30")

    text = env_file.read_text()
    assert "SYNC_TIME=10:15" in text
    assert "NOTIFY_TIME=11:30" in text
    assert "DISCORD_TOKEN=tok" in text
    assert text.count("SYNC_TIME=") == 1
    assert text.count("NOTIFY_TIME=") == 1


def test_update_schedule_appends_when_missing(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=tok\n")

    update_schedule(env_file, sync_time="10:15", notify_time="11:30")

    text = env_file.read_text()
    assert "SYNC_TIME=10:15" in text
    assert "NOTIFY_TIME=11:30" in text


def test_update_schedule_validates_format(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=tok\n")
    with pytest.raises(ConfigError):
        update_schedule(env_file, sync_time="bad", notify_time="11:30")
```

- [ ] **Step 2: Run tests; confirm failure**

Run: `pytest tests/presentation/discord_bot/test_config.py -v`
Expected: ImportError or collection error for `updater.presentation.discord_bot.config`.

- [ ] **Step 3: Implement the config module**

`src/updater/presentation/discord_bot/config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class BotConfig:
    env_path: Path
    discord_token: str
    guild_id: int
    channel_id: int
    admin_role_id: int
    sync_time: tuple[int, int]
    notify_time: tuple[int, int]
    mongodb_uri: str
    mongodb_database: str


_REQUIRED_STR = ("DISCORD_TOKEN",)
_REQUIRED_INT = ("DISCORD_GUILD_ID", "DISCORD_CHANNEL_ID", "DISCORD_ADMIN_ROLE_ID")
_REQUIRED_TIME = ("SYNC_TIME", "NOTIFY_TIME")


def parse_time(value: str) -> tuple[int, int]:
    if not isinstance(value, str):
        raise ConfigError(f"time must be a string, got {value!r}")
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ConfigError(f"time must be HH:MM, got {value!r}")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ConfigError(f"time must be HH:MM, got {value!r}") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ConfigError(f"time out of range, got {value!r}")
    return hour, minute


def load_config(env_path: Path) -> BotConfig:
    values = dotenv_values(env_path)

    def _require(key: str) -> str:
        raw = values.get(key)
        if raw is None or raw.strip() == "":
            raise ConfigError(f"{key} is required in {env_path}")
        return raw.strip()

    for key in _REQUIRED_STR + _REQUIRED_INT + _REQUIRED_TIME:
        _require(key)

    int_fields: dict[str, int] = {}
    for key in _REQUIRED_INT:
        raw = _require(key)
        try:
            int_fields[key] = int(raw)
        except ValueError as exc:
            raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc

    time_fields: dict[str, tuple[int, int]] = {}
    for key in _REQUIRED_TIME:
        try:
            time_fields[key] = parse_time(_require(key))
        except ConfigError as exc:
            raise ConfigError(f"{key}: {exc}") from exc

    return BotConfig(
        env_path=env_path,
        discord_token=_require("DISCORD_TOKEN"),
        guild_id=int_fields["DISCORD_GUILD_ID"],
        channel_id=int_fields["DISCORD_CHANNEL_ID"],
        admin_role_id=int_fields["DISCORD_ADMIN_ROLE_ID"],
        sync_time=time_fields["SYNC_TIME"],
        notify_time=time_fields["NOTIFY_TIME"],
        mongodb_uri=(values.get("MONGODB_URI") or "mongodb://localhost:27017").strip(),
        mongodb_database=(values.get("MONGODB_DATABASE") or "pwn2own_updater").strip(),
    )


def update_schedule(env_path: Path, *, sync_time: str, notify_time: str) -> None:
    parse_time(sync_time)
    parse_time(notify_time)

    lines = env_path.read_text().splitlines() if env_path.exists() else []
    updates = {"SYNC_TIME": sync_time, "NOTIFY_TIME": notify_time}

    seen: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if "=" not in stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            new_lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines) + "\n")
```

- [ ] **Step 4: Run tests; confirm they pass**

Run: `pytest tests/presentation/discord_bot/test_config.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/presentation/discord_bot/config.py tests/presentation/discord_bot/test_config.py
git commit -m "feat(bot): add .env config loader and schedule writer"
```

---

## Task 6: Permissions (admin role check)

**Files:**
- Create: `src/updater/presentation/discord_bot/permissions.py`
- Create: `tests/presentation/discord_bot/test_permissions.py`

- [ ] **Step 1: Write the failing tests**

`tests/presentation/discord_bot/test_permissions.py`:

```python
from updater.presentation.discord_bot.permissions import has_admin_role


class FakeRole:
    def __init__(self, role_id):
        self.id = role_id


class FakeMember:
    def __init__(self, role_ids):
        self.roles = [FakeRole(r) for r in role_ids]


def test_member_with_admin_role_passes():
    member = FakeMember([100, 333, 200])
    assert has_admin_role(member, admin_role_id=333) is True


def test_member_without_admin_role_fails():
    member = FakeMember([100, 200])
    assert has_admin_role(member, admin_role_id=333) is False


def test_user_without_roles_attribute_fails():
    class UserOnly:
        pass

    assert has_admin_role(UserOnly(), admin_role_id=333) is False
```

- [ ] **Step 2: Run; confirm failure**

Run: `pytest tests/presentation/discord_bot/test_permissions.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

`src/updater/presentation/discord_bot/permissions.py`:

```python
from __future__ import annotations

from typing import Any


def has_admin_role(member: Any, *, admin_role_id: int) -> bool:
    roles = getattr(member, "roles", None)
    if not roles:
        return False
    return any(getattr(role, "id", None) == admin_role_id for role in roles)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/presentation/discord_bot/test_permissions.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/presentation/discord_bot/permissions.py tests/presentation/discord_bot/test_permissions.py
git commit -m "feat(bot): add admin role check"
```

---

## Task 7: Formatting (severity colors, embeds, summary)

**Files:**
- Create: `src/updater/presentation/discord_bot/formatting.py`
- Create: `tests/presentation/discord_bot/test_formatting.py`

- [ ] **Step 1: Write the failing tests**

`tests/presentation/discord_bot/test_formatting.py`:

```python
from datetime import date

from updater.presentation.discord_bot.formatting import (
    SEVERITY_COLORS,
    build_finding_embed,
    build_summary_message,
    group_findings,
)


def _finding(
    advisory_id="CVE-2024-12647",
    aliases=None,
    cvss_score=7.8,
    severity="HIGH",
    description="desc",
    references=None,
    target_names=("Canon MF654Cdw",),
):
    return {
        "advisory_id": advisory_id,
        "aliases": list(aliases or []),
        "cvss_score": cvss_score,
        "severity": severity,
        "description": description,
        "references": list(references or []),
        "target_names": list(target_names),
    }


def test_severity_colors_match_spec():
    assert SEVERITY_COLORS["CRITICAL"] == 0xCC0000
    assert SEVERITY_COLORS["HIGH"] == 0xFF7700
    assert SEVERITY_COLORS["MEDIUM"] == 0xFFCC00
    assert SEVERITY_COLORS["LOW"] == 0x28A745
    assert SEVERITY_COLORS["INFORMATIONAL"] == 0x999999
    assert SEVERITY_COLORS["NONE"] == 0x999999


def test_embed_uses_cve_id_when_available():
    embed = build_finding_embed(_finding(advisory_id="CVE-2024-12647"))
    assert embed.title == "CVE-2024-12647"


def test_embed_uses_zdi_id_when_no_cve():
    finding = _finding(advisory_id="ZDI-26-280", aliases=[])
    embed = build_finding_embed(finding)
    assert embed.title == "ZDI-26-280"


def test_embed_prefers_cve_alias_over_zdi_advisory_id():
    finding = _finding(advisory_id="ZDI-26-280", aliases=["CVE-2024-99999"])
    embed = build_finding_embed(finding)
    assert embed.title == "CVE-2024-99999"


def test_embed_joins_multiple_target_names():
    finding = _finding(target_names=("Canon MF654Cdw", "Canon MF656Cdw"))
    embed = build_finding_embed(finding)
    target_field = next(f for f in embed.fields if f.name == "Target")
    assert target_field.value == "Canon MF654Cdw, Canon MF656Cdw"


def test_embed_color_matches_severity():
    embed = build_finding_embed(_finding(severity="HIGH"))
    assert embed.color.value == 0xFF7700


def test_embed_color_falls_back_to_grey_for_unknown_severity():
    embed = build_finding_embed(_finding(severity=None))
    assert embed.color.value == 0x999999


def test_embed_includes_cvss_and_description():
    embed = build_finding_embed(_finding(cvss_score=7.8, description="some text"))
    fields = {f.name: f.value for f in embed.fields}
    assert fields["CVSS"] == "7.8"
    assert "some text" in embed.description


def test_embed_lists_references_as_bullets():
    finding = _finding(references=["https://a", "https://b"])
    embed = build_finding_embed(finding)
    fields = {f.name: f.value for f in embed.fields}
    assert "- https://a" in fields["References"]
    assert "- https://b" in fields["References"]


def test_summary_message_format():
    msg = build_summary_message(
        report_date=date(2026, 5, 20),
        targets_processed=5,
        new_findings=3,
        errors=0,
    )
    assert msg == (
        "Daily Vulnerability Report — 2026-05-20\n"
        "Targets processed: 5\n"
        "New findings: 3\n"
        "Errors: 0"
    )


def test_group_findings_merges_same_vulnerability():
    snapshot = {
        "target_vulnerabilities": [
            {
                "advisory_id": "CVE-2024-12647",
                "aliases": [],
                "cvss_score": 7.8,
                "severity": "HIGH",
                "description": "desc",
                "references": ["https://x"],
                "affected_targets": [
                    {"target_name": "Canon MF654Cdw"},
                    {"target_name": "Canon MF656Cdw"},
                ],
            }
        ]
    }
    findings = group_findings(snapshot)
    assert len(findings) == 1
    assert findings[0]["target_names"] == ["Canon MF654Cdw", "Canon MF656Cdw"]
    assert findings[0]["advisory_id"] == "CVE-2024-12647"
```

- [ ] **Step 2: Run; confirm failure**

Run: `pytest tests/presentation/discord_bot/test_formatting.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

`src/updater/presentation/discord_bot/formatting.py`:

```python
from __future__ import annotations

from datetime import date
from typing import Any, Iterable

import discord


SEVERITY_COLORS: dict[str, int] = {
    "CRITICAL": 0xCC0000,
    "HIGH": 0xFF7700,
    "MEDIUM": 0xFFCC00,
    "LOW": 0x28A745,
    "INFORMATIONAL": 0x999999,
    "NONE": 0x999999,
}


def _pick_title(advisory_id: str, aliases: Iterable[str]) -> str:
    if advisory_id.upper().startswith("CVE-"):
        return advisory_id
    for alias in aliases:
        if alias.upper().startswith("CVE-"):
            return alias
    return advisory_id


def _color_for(severity: str | None) -> int:
    if not severity:
        return SEVERITY_COLORS["NONE"]
    return SEVERITY_COLORS.get(severity.upper(), SEVERITY_COLORS["NONE"])


def build_finding_embed(finding: dict[str, Any]) -> discord.Embed:
    advisory_id = finding["advisory_id"]
    aliases = finding.get("aliases") or []
    title = _pick_title(advisory_id, aliases)
    description = finding.get("description") or ""
    severity = finding.get("severity") or "None"

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color(_color_for(finding.get("severity"))),
    )

    target_names = finding.get("target_names") or []
    embed.add_field(name="Target", value=", ".join(target_names) or "—", inline=False)
    embed.add_field(name="Severity", value=severity, inline=True)

    cvss = finding.get("cvss_score")
    embed.add_field(name="CVSS", value="—" if cvss is None else f"{cvss}", inline=True)

    references = finding.get("references") or []
    if references:
        embed.add_field(
            name="References",
            value="\n".join(f"- {ref}" for ref in references),
            inline=False,
        )

    return embed


def build_summary_message(
    *,
    report_date: date,
    targets_processed: int,
    new_findings: int,
    errors: int,
) -> str:
    return (
        f"Daily Vulnerability Report — {report_date.isoformat()}\n"
        f"Targets processed: {targets_processed}\n"
        f"New findings: {new_findings}\n"
        f"Errors: {errors}"
    )


def group_findings(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten an ExportService snapshot into a list of finding dicts for embedding."""
    findings: list[dict[str, Any]] = []
    for entry in snapshot.get("target_vulnerabilities", []):
        target_names = [
            t.get("target_name") for t in entry.get("affected_targets", []) if t.get("target_name")
        ]
        findings.append(
            {
                "advisory_id": entry.get("advisory_id", ""),
                "aliases": list(entry.get("aliases") or []),
                "cvss_score": entry.get("cvss_score"),
                "severity": entry.get("severity"),
                "description": entry.get("description") or "",
                "references": list(entry.get("references") or []),
                "target_names": target_names,
            }
        )
    return findings
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/presentation/discord_bot/test_formatting.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/presentation/discord_bot/formatting.py tests/presentation/discord_bot/test_formatting.py
git commit -m "feat(bot): add embed and summary formatting"
```

---

## Task 8: Scheduler "should fire" tracker

**Files:**
- Create: `src/updater/presentation/discord_bot/scheduler.py`
- Create: `tests/presentation/discord_bot/test_scheduler.py`

- [ ] **Step 1: Write the failing tests**

`tests/presentation/discord_bot/test_scheduler.py`:

```python
from datetime import datetime, timezone

from updater.presentation.discord_bot.scheduler import FireTracker


def _at(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def test_fires_when_current_time_passes_configured_time():
    tracker = FireTracker()
    result = tracker.check(
        now=_at(2026, 5, 20, 8, 0),
        sync_time=(8, 0),
        notify_time=(9, 0),
    )
    assert result == ("sync",)


def test_does_not_fire_before_configured_time():
    tracker = FireTracker()
    result = tracker.check(
        now=_at(2026, 5, 20, 7, 59),
        sync_time=(8, 0),
        notify_time=(9, 0),
    )
    assert result == ()


def test_fires_each_event_once_per_day():
    tracker = FireTracker()
    tracker.check(now=_at(2026, 5, 20, 8, 0), sync_time=(8, 0), notify_time=(9, 0))
    result = tracker.check(now=_at(2026, 5, 20, 8, 1), sync_time=(8, 0), notify_time=(9, 0))
    assert result == ()


def test_fires_sync_and_notify_on_next_day():
    tracker = FireTracker()
    tracker.check(now=_at(2026, 5, 20, 8, 0), sync_time=(8, 0), notify_time=(9, 0))
    tracker.check(now=_at(2026, 5, 20, 9, 0), sync_time=(8, 0), notify_time=(9, 0))
    result_next_day_sync = tracker.check(
        now=_at(2026, 5, 21, 8, 0), sync_time=(8, 0), notify_time=(9, 0)
    )
    assert result_next_day_sync == ("sync",)
    result_next_day_notify = tracker.check(
        now=_at(2026, 5, 21, 9, 0), sync_time=(8, 0), notify_time=(9, 0)
    )
    assert result_next_day_notify == ("notify",)


def test_late_check_still_fires_once():
    """If the bot starts at 10:00 with sync_time=08:00, sync should still fire."""
    tracker = FireTracker()
    result = tracker.check(
        now=_at(2026, 5, 20, 10, 0),
        sync_time=(8, 0),
        notify_time=(9, 0),
    )
    assert set(result) == {"sync", "notify"}


def test_schedule_change_takes_effect():
    tracker = FireTracker()
    tracker.check(now=_at(2026, 5, 20, 8, 0), sync_time=(8, 0), notify_time=(9, 0))
    # change schedule, sync fires again same day at the new time
    result = tracker.check(
        now=_at(2026, 5, 20, 11, 0),
        sync_time=(11, 0),
        notify_time=(12, 0),
    )
    assert result == ("sync",)
```

- [ ] **Step 2: Run; confirm failure**

Run: `pytest tests/presentation/discord_bot/test_scheduler.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

`src/updater/presentation/discord_bot/scheduler.py`:

```python
from __future__ import annotations

from datetime import datetime


class FireTracker:
    """Pure state machine deciding whether sync/notify should fire on this tick.

    Each event fires at most once per (date, configured_time) pair. Changing the
    configured time on the same day re-arms the corresponding event.
    """

    def __init__(self) -> None:
        self._last_fired: dict[str, tuple[str, tuple[int, int]]] = {}

    def check(
        self,
        *,
        now: datetime,
        sync_time: tuple[int, int],
        notify_time: tuple[int, int],
    ) -> tuple[str, ...]:
        fired: list[str] = []
        for event, configured in (("sync", sync_time), ("notify", notify_time)):
            if self._should_fire(event, now, configured):
                self._last_fired[event] = (now.date().isoformat(), configured)
                fired.append(event)
        return tuple(fired)

    def _should_fire(
        self, event: str, now: datetime, configured: tuple[int, int]
    ) -> bool:
        hour, minute = configured
        if (now.hour, now.minute) < (hour, minute):
            return False
        previous = self._last_fired.get(event)
        if previous is None:
            return True
        prev_date, prev_configured = previous
        return prev_date != now.date().isoformat() or prev_configured != configured
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/presentation/discord_bot/test_scheduler.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/presentation/discord_bot/scheduler.py tests/presentation/discord_bot/test_scheduler.py
git commit -m "feat(bot): add daily fire tracker for sync/notify"
```

---

## Task 9: Pure command handlers

**Files:**
- Create: `src/updater/presentation/discord_bot/commands.py`
- Create: `tests/presentation/discord_bot/test_commands.py`

This task defines async handlers that take their dependencies explicitly. `bot.py` (Task 10) will translate `discord.Interaction` into these calls. Handlers return `CommandResult`, a dataclass holding text + embeds.

- [ ] **Step 1: Write the failing tests for `CommandResult` plumbing + happy paths**

`tests/presentation/discord_bot/test_commands.py`:

```python
import pytest

from updater.domain.models import Target, TargetVulnerability, Vulnerability
from updater.presentation.discord_bot.commands import (
    CommandResult,
    Services,
    handle_add_target,
    handle_add_vuln,
    handle_import_targets,
    handle_list_targets,
    handle_remove_target,
    handle_set_schedule,
    handle_show_schedule,
    handle_show_target,
    handle_sync_cves,
)


class FakeTargetRepo:
    def __init__(self, targets=None):
        self._targets = list(targets or [])

    def upsert(self, target):
        target.id = target.id or f"target-{len(self._targets) + 1}"
        self._targets.append(target)
        return target

    def list_all(self):
        return list(self._targets)

    def find_by_name(self, name):
        norm = name.strip().lower()
        return next((t for t in self._targets if t.name.lower() == norm), None)

    def delete(self, name):
        norm = name.strip().lower()
        for i, t in enumerate(self._targets):
            if t.name.lower() == norm:
                self._targets.pop(i)
                return True
        return False


class FakeVersionRepo:
    def __init__(self):
        self.calls = []

    def upsert(self, version):
        self.calls.append(version)
        return version


class FakeVulnRepo:
    def __init__(self, items=None):
        self.items = {v.advisory_id: v for v in (items or [])}

    def upsert(self, vuln):
        vuln.id = vuln.id or vuln.advisory_id
        self.items[vuln.advisory_id] = vuln
        return vuln

    def list_all(self):
        return list(self.items.values())


class FakeLinkRepo:
    def __init__(self, links=None):
        self.links = list(links or [])

    def upsert(self, link):
        link.id = link.id or f"link-{len(self.links) + 1}"
        self.links.append(link)
        return link

    def list_all(self):
        return list(self.links)

    def delete_by_target(self, target_id):
        before = len(self.links)
        self.links = [l for l in self.links if l.target_id != target_id]
        return before - len(self.links)


def _services(target_repo=None, vuln_repo=None, link_repo=None, version_repo=None, sources=None):
    return Services(
        target_repo=target_repo or FakeTargetRepo(),
        version_repo=version_repo or FakeVersionRepo(),
        vulnerability_repo=vuln_repo or FakeVulnRepo(),
        target_vulnerability_repo=link_repo or FakeLinkRepo(),
        sources=sources or [],
    )


async def test_list_targets_empty():
    result = await handle_list_targets(_services())
    assert isinstance(result, CommandResult)
    assert "No targets" in result.text


async def test_list_targets_returns_names():
    services = _services(target_repo=FakeTargetRepo([
        Target(id="t1", name="Adobe Reader"),
        Target(id="t2", name="Canon MF654Cdw"),
    ]))
    result = await handle_list_targets(services)
    assert "Adobe Reader" in result.text
    assert "Canon MF654Cdw" in result.text


async def test_show_target_includes_vulnerability_count():
    target = Target(id="t1", name="Adobe Reader")
    link = TargetVulnerability(target_id="t1", vulnerability_id="v1")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        link_repo=FakeLinkRepo([link]),
    )
    result = await handle_show_target(services, name="Adobe Reader")
    assert "Adobe Reader" in result.text
    assert "1" in result.text


async def test_show_target_not_found():
    result = await handle_show_target(_services(), name="Nope")
    assert "not found" in result.text.lower()


async def test_add_target_creates_target():
    services = _services()
    result = await handle_add_target(
        services,
        name="Adobe Reader",
        aliases=["Acrobat"],
        vendor="Adobe",
        category="pdf",
    )
    assert "Added" in result.text
    saved = services.target_repo.list_all()
    assert saved[0].name == "Adobe Reader"
    assert saved[0].aliases == ["Acrobat"]
    assert saved[0].vendor == "Adobe"
    assert saved[0].category == "pdf"


async def test_remove_target_removes_target_and_links():
    target = Target(id="t1", name="Adobe Reader")
    link = TargetVulnerability(target_id="t1", vulnerability_id="v1")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        link_repo=FakeLinkRepo([link]),
    )
    result = await handle_remove_target(services, names=["Adobe Reader"])
    assert "Removed" in result.text
    assert services.target_repo.list_all() == []
    assert services.target_vulnerability_repo.list_all() == []


async def test_remove_target_reports_missing():
    services = _services()
    result = await handle_remove_target(services, names=["Adobe Reader"])
    assert "not found" in result.text.lower()


async def test_import_targets_imports_csv_bytes():
    csv_text = "name,aliases,vendor\nAdobe Reader,Acrobat,Adobe\n"
    services = _services()
    result = await handle_import_targets(services, csv_bytes=csv_text.encode())
    assert "imported" in result.text.lower()
    assert services.target_repo.list_all()[0].name == "Adobe Reader"


async def test_add_vuln_without_target_creates_vulnerability_only():
    services = _services()
    result = await handle_add_vuln(
        services,
        advisory_id="CVE-2024-12647",
        description="boom",
        cvss_score=7.8,
        severity="HIGH",
        references=["https://x"],
        target_name=None,
    )
    assert "Added" in result.text
    assert services.vulnerability_repo.list_all()[0].advisory_id == "CVE-2024-12647"
    assert services.target_vulnerability_repo.list_all() == []


async def test_add_vuln_with_target_creates_link():
    services = _services(target_repo=FakeTargetRepo([Target(id="t1", name="Canon")]))
    result = await handle_add_vuln(
        services,
        advisory_id="CVE-2024-12647",
        description="boom",
        cvss_score=7.8,
        severity="HIGH",
        references=[],
        target_name="Canon",
    )
    assert "Added" in result.text
    assert services.target_vulnerability_repo.list_all()[0].target_id == "t1"


async def test_add_vuln_with_unknown_target_returns_error():
    services = _services()
    result = await handle_add_vuln(
        services,
        advisory_id="CVE-1",
        description="",
        cvss_score=None,
        severity=None,
        references=[],
        target_name="Nope",
    )
    assert "not found" in result.text.lower()
    assert services.vulnerability_repo.list_all() == []


class _FakeSource:
    source_name = "fake"

    def search(self, target, query, since_year=None):
        if query == "Canon":
            return [(
                Vulnerability(advisory_id="CVE-2024-1", sources=["fake"], severity="HIGH", description="d"),
                {"matched": query},
            )]
        return []


async def test_sync_cves_returns_embeds_for_findings():
    target = Target(id="t1", name="Canon")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        sources=[_FakeSource()],
    )
    result = await handle_sync_cves(services, target_name="Canon")
    assert any("Sync" in line for line in result.text.splitlines())
    assert len(result.embeds) == 1
    assert result.embeds[0].title == "CVE-2024-1"


async def test_set_schedule_writes_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=tok\nSYNC_TIME=08:00\nNOTIFY_TIME=09:00\n")
    result = await handle_set_schedule(
        _services(),
        env_path=env_file,
        sync_time="10:15",
        notify_time="11:30",
    )
    assert "10:15" in result.text
    assert "11:30" in result.text
    assert "SYNC_TIME=10:15" in env_file.read_text()


async def test_set_schedule_rejects_invalid(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=tok\n")
    result = await handle_set_schedule(
        _services(),
        env_path=env_file,
        sync_time="25:00",
        notify_time="09:00",
    )
    assert "invalid" in result.text.lower()


async def test_show_schedule_displays_current_times():
    result = await handle_show_schedule(sync_time=(8, 0), notify_time=(9, 30))
    assert "08:00" in result.text
    assert "09:30" in result.text
```

- [ ] **Step 2: Run; confirm failure**

Run: `pytest tests/presentation/discord_bot/test_commands.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement command handlers**

`src/updater/presentation/discord_bot/commands.py`:

```python
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import discord

from updater.application.export_json import ExportService
from updater.application.import_targets import ImportTargetsService
from updater.application.sync_vulnerabilities import SyncVulnerabilitiesService
from updater.domain.models import Target, TargetVersion, TargetVulnerability, Vulnerability
from updater.domain.repositories import (
    TargetRepository,
    TargetVersionRepository,
    TargetVulnerabilityRepository,
    VulnerabilityRepository,
    VulnerabilitySource,
)
from updater.infrastructure.csv_loader import CsvTargetLoader
from updater.presentation.discord_bot.config import ConfigError, update_schedule
from updater.presentation.discord_bot.formatting import (
    build_finding_embed,
    group_findings,
)


@dataclass
class CommandResult:
    text: str = ""
    embeds: list[discord.Embed] = field(default_factory=list)


@dataclass
class Services:
    target_repo: TargetRepository
    version_repo: TargetVersionRepository
    vulnerability_repo: VulnerabilityRepository
    target_vulnerability_repo: TargetVulnerabilityRepository
    sources: list[VulnerabilitySource]


async def handle_list_targets(services: Services) -> CommandResult:
    targets = services.target_repo.list_all()
    if not targets:
        return CommandResult(text="No targets configured.")
    lines = [f"- {t.name}" for t in targets]
    return CommandResult(text="Targets:\n" + "\n".join(lines))


async def handle_show_target(services: Services, *, name: str) -> CommandResult:
    target = services.target_repo.find_by_name(name)
    if target is None:
        return CommandResult(text=f"Target {name!r} not found.")
    target_id = target.id or target.normalized_name
    linked = sum(
        1
        for link in services.target_vulnerability_repo.list_all()
        if link.target_id == target_id
    )
    lines = [
        f"Name: {target.name}",
        f"Aliases: {', '.join(target.aliases) or '—'}",
        f"Vendor: {target.vendor or '—'}",
        f"Category: {target.category or '—'}",
        f"Vulnerabilities: {linked}",
    ]
    return CommandResult(text="\n".join(lines))


async def handle_add_target(
    services: Services,
    *,
    name: str,
    aliases: list[str] | None = None,
    vendor: str | None = None,
    category: str | None = None,
) -> CommandResult:
    target = Target(
        name=name,
        aliases=list(aliases or []),
        vendor=vendor,
        category=category,
    )
    services.target_repo.upsert(target)
    return CommandResult(text=f"Added target: {name}")


async def handle_remove_target(services: Services, *, names: list[str]) -> CommandResult:
    removed: list[str] = []
    missing: list[str] = []
    for name in names:
        target = services.target_repo.find_by_name(name)
        if target is None:
            missing.append(name)
            continue
        target_id = target.id or target.normalized_name
        services.target_vulnerability_repo.delete_by_target(target_id)
        services.target_repo.delete(name)
        removed.append(name)

    parts: list[str] = []
    if removed:
        parts.append("Removed: " + ", ".join(removed))
    if missing:
        parts.append("Not found: " + ", ".join(missing))
    return CommandResult(text="\n".join(parts) or "Nothing to do.")


async def handle_import_targets(services: Services, *, csv_bytes: bytes) -> CommandResult:
    import tempfile

    with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as tmp:
        tmp.write(csv_bytes)
        tmp_path = Path(tmp.name)

    try:
        load_result = CsvTargetLoader().load(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    import_result = ImportTargetsService(
        services.target_repo, services.version_repo
    ).import_items([(item.target, item.version) for item in load_result.items])

    lines = [
        "Import complete.",
        f"Targets imported: {import_result.targets_imported}",
        f"Versions imported: {import_result.versions_imported}",
        f"Errors: {len(load_result.errors)}",
    ]
    lines.extend(load_result.errors[:10])
    return CommandResult(text="\n".join(lines))


async def handle_add_vuln(
    services: Services,
    *,
    advisory_id: str,
    description: str,
    cvss_score: float | None,
    severity: str | None,
    references: list[str],
    target_name: str | None,
) -> CommandResult:
    target = None
    if target_name:
        target = services.target_repo.find_by_name(target_name)
        if target is None:
            return CommandResult(text=f"Target {target_name!r} not found.")

    vuln = Vulnerability(
        advisory_id=advisory_id,
        description=description or None,
        cvss_score=cvss_score,
        severity=severity,
        references=list(references),
        sources=["manual"],
    )
    saved = services.vulnerability_repo.upsert(vuln)

    if target is not None:
        link = TargetVulnerability(
            target_id=target.id or target.normalized_name,
            target_name=target.name,
            vulnerability_id=saved.id or saved.advisory_id,
        )
        link.add_evidence(source="manual", matched_query=target.name, evidence={"source": "manual"})
        services.target_vulnerability_repo.upsert(link)

    return CommandResult(text=f"Added vulnerability: {advisory_id}")


async def handle_sync_cves(services: Services, *, target_name: str | None) -> CommandResult:
    sync = SyncVulnerabilitiesService(
        services.target_repo,
        services.vulnerability_repo,
        services.target_vulnerability_repo,
        services.sources,
    )
    result = sync.sync_one(target_name) if target_name else sync.sync_all()

    snapshot = ExportService(
        services.target_repo,
        services.vulnerability_repo,
        services.target_vulnerability_repo,
    ).snapshot()
    findings = group_findings(snapshot)

    if target_name:
        findings = [
            f for f in findings if target_name.strip().lower() in [t.lower() for t in f["target_names"]]
        ]

    summary = (
        f"Sync complete. targets_processed={result.targets_processed} "
        f"vulnerabilities_seen={result.vulnerabilities_seen} "
        f"links_updated={result.links_updated} errors={len(result.errors)}"
    )
    embeds = [build_finding_embed(f) for f in findings]
    return CommandResult(text=summary, embeds=embeds)


async def handle_set_schedule(
    services: Services,
    *,
    env_path: Path,
    sync_time: str,
    notify_time: str,
) -> CommandResult:
    try:
        update_schedule(env_path, sync_time=sync_time, notify_time=notify_time)
    except ConfigError as exc:
        return CommandResult(text=f"Invalid schedule: {exc}")
    return CommandResult(text=f"Schedule updated. SYNC_TIME={sync_time}, NOTIFY_TIME={notify_time}")


async def handle_show_schedule(
    *, sync_time: tuple[int, int], notify_time: tuple[int, int]
) -> CommandResult:
    return CommandResult(
        text=(
            f"SYNC_TIME={sync_time[0]:02d}:{sync_time[1]:02d}\n"
            f"NOTIFY_TIME={notify_time[0]:02d}:{notify_time[1]:02d}"
        )
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/presentation/discord_bot/test_commands.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/presentation/discord_bot/commands.py tests/presentation/discord_bot/test_commands.py
git commit -m "feat(bot): add pure async command handlers"
```

---

## Task 10: Bot entrypoint, command tree, scheduler loop

This task wires `discord.py` to the handlers. The handlers are already tested; this file is mostly glue. We keep tests light here (a smoke test that imports `main` and `build_client`).

**Files:**
- Create: `src/updater/presentation/discord_bot/bot.py`
- Modify: `src/updater/__main__.py`
- Add a small smoke test: append to `tests/presentation/discord_bot/test_commands.py` (one test).

- [ ] **Step 1: Write the failing smoke test**

Append to `tests/presentation/discord_bot/test_commands.py`:

```python
def test_bot_module_exposes_main_and_build_client():
    from updater.presentation.discord_bot import bot

    assert callable(bot.main)
    assert callable(bot.build_client)
```

- [ ] **Step 2: Run; confirm failure**

Run: `pytest tests/presentation/discord_bot/test_commands.py::test_bot_module_exposes_main_and_build_client -v`
Expected: ImportError for `bot`.

- [ ] **Step 3: Implement `bot.py`**

`src/updater/presentation/discord_bot/bot.py`:

```python
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import tasks

from updater.application.export_json import ExportService
from updater.application.sync_vulnerabilities import SyncVulnerabilitiesService
from updater.infrastructure.mongo import (
    MongoDatabase,
    MongoTargetRepository,
    MongoTargetVersionRepository,
    MongoTargetVulnerabilityRepository,
    MongoVulnerabilityRepository,
)
from updater.infrastructure.sources.nvd import NvdSource
from updater.infrastructure.sources.zdi import ZdiSource
from updater.presentation.discord_bot import commands as cmd
from updater.presentation.discord_bot.config import BotConfig, ConfigError, load_config
from updater.presentation.discord_bot.formatting import (
    build_finding_embed,
    build_summary_message,
    group_findings,
)
from updater.presentation.discord_bot.permissions import has_admin_role
from updater.presentation.discord_bot.scheduler import FireTracker


log = logging.getLogger("updater.bot")


def build_client(config: BotConfig) -> discord.Client:
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = False
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)
    guild = discord.Object(id=config.guild_id)

    services = _build_services(config)
    tracker = FireTracker()

    async def _admin_only(interaction: discord.Interaction) -> bool:
        if not has_admin_role(interaction.user, admin_role_id=config.admin_role_id):
            await interaction.response.send_message(
                "Admin role required.", ephemeral=True
            )
            return False
        return True

    async def _reply(interaction: discord.Interaction, result: cmd.CommandResult, *, ephemeral=False):
        await interaction.response.send_message(
            content=result.text or None,
            embeds=result.embeds,
            ephemeral=ephemeral,
        )

    @tree.command(name="list-targets", description="List all targets", guild=guild)
    async def list_targets(interaction: discord.Interaction):
        await _reply(interaction, await cmd.handle_list_targets(services))

    @tree.command(name="show-target", description="Show target details", guild=guild)
    @app_commands.describe(name="Target name")
    async def show_target(interaction: discord.Interaction, name: str):
        await _reply(interaction, await cmd.handle_show_target(services, name=name))

    @tree.command(name="add-target", description="Add a target", guild=guild)
    @app_commands.describe(
        name="Target name",
        aliases="Semicolon-separated aliases",
        vendor="Vendor",
        category="Category",
    )
    async def add_target(
        interaction: discord.Interaction,
        name: str,
        aliases: str | None = None,
        vendor: str | None = None,
        category: str | None = None,
    ):
        if not await _admin_only(interaction):
            return
        alias_list = [a.strip() for a in (aliases or "").split(";") if a.strip()]
        await _reply(
            interaction,
            await cmd.handle_add_target(
                services, name=name, aliases=alias_list, vendor=vendor, category=category
            ),
        )

    @tree.command(name="remove-target", description="Remove one or more targets", guild=guild)
    @app_commands.describe(names="Comma-separated target names")
    async def remove_target(interaction: discord.Interaction, names: str):
        if not await _admin_only(interaction):
            return
        name_list = [n.strip() for n in names.split(",") if n.strip()]
        await _reply(interaction, await cmd.handle_remove_target(services, names=name_list))

    @tree.command(name="import-targets", description="Import targets from a CSV file", guild=guild)
    async def import_targets(interaction: discord.Interaction, file: discord.Attachment):
        if not await _admin_only(interaction):
            return
        await interaction.response.defer(thinking=True)
        data = await file.read()
        result = await cmd.handle_import_targets(services, csv_bytes=data)
        await interaction.followup.send(content=result.text)

    @tree.command(name="add-vuln", description="Manually add a vulnerability", guild=guild)
    @app_commands.describe(
        advisory_id="Advisory ID (e.g. CVE-2024-12647)",
        description="Description",
        cvss_score="CVSS score",
        severity="Severity (CRITICAL/HIGH/MEDIUM/LOW/INFORMATIONAL/NONE)",
        references="Comma-separated reference URLs",
        target_name="Optional target name to link",
    )
    async def add_vuln(
        interaction: discord.Interaction,
        advisory_id: str,
        description: str,
        cvss_score: float | None = None,
        severity: str | None = None,
        references: str | None = None,
        target_name: str | None = None,
    ):
        if not await _admin_only(interaction):
            return
        ref_list = [r.strip() for r in (references or "").split(",") if r.strip()]
        await _reply(
            interaction,
            await cmd.handle_add_vuln(
                services,
                advisory_id=advisory_id,
                description=description,
                cvss_score=cvss_score,
                severity=severity,
                references=ref_list,
                target_name=target_name,
            ),
        )

    @tree.command(name="sync-cves", description="Sync vulnerabilities now", guild=guild)
    @app_commands.describe(target="Optional target name; omit to sync all")
    async def sync_cves(interaction: discord.Interaction, target: str | None = None):
        if not await _admin_only(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        result = await cmd.handle_sync_cves(services, target_name=target)
        await interaction.followup.send(
            content=result.text or None, embeds=result.embeds, ephemeral=True
        )

    @tree.command(name="set-schedule", description="Set daily sync and notify times", guild=guild)
    @app_commands.describe(sync_time="HH:MM", notify_time="HH:MM")
    async def set_schedule(interaction: discord.Interaction, sync_time: str, notify_time: str):
        if not await _admin_only(interaction):
            return
        result = await cmd.handle_set_schedule(
            services,
            env_path=config.env_path,
            sync_time=sync_time,
            notify_time=notify_time,
        )
        await _reply(interaction, result)

    @tree.command(name="show-schedule", description="Show current schedule", guild=guild)
    async def show_schedule(interaction: discord.Interaction):
        current = _reload_or_keep(config)
        await _reply(
            interaction,
            await cmd.handle_show_schedule(
                sync_time=current.sync_time, notify_time=current.notify_time
            ),
        )

    @client.event
    async def on_ready():
        await tree.sync(guild=guild)
        log.info("Bot ready. Commands synced to guild %s.", config.guild_id)
        if not _scheduler_loop.is_running():
            _scheduler_loop.start()

    @tasks.loop(seconds=60)
    async def _scheduler_loop():
        try:
            current = _reload_or_keep(config)
            events = tracker.check(
                now=datetime.now(timezone.utc),
                sync_time=current.sync_time,
                notify_time=current.notify_time,
            )
            channel = client.get_channel(config.channel_id)
            for event in events:
                if event == "sync":
                    await _run_sync(services)
                elif event == "notify":
                    if channel is not None:
                        await _run_notify(services, channel)
        except Exception:
            log.exception("scheduler tick failed")

    return client


def _reload_or_keep(default_config: BotConfig) -> BotConfig:
    try:
        return load_config(default_config.env_path)
    except ConfigError:
        return default_config


def _build_services(config: BotConfig) -> cmd.Services:
    db = MongoDatabase(uri=config.mongodb_uri, database=config.mongodb_database)
    return cmd.Services(
        target_repo=MongoTargetRepository(db.db),
        version_repo=MongoTargetVersionRepository(db.db),
        vulnerability_repo=MongoVulnerabilityRepository(db.db),
        target_vulnerability_repo=MongoTargetVulnerabilityRepository(db.db),
        sources=[NvdSource(), ZdiSource()],
    )


async def _run_sync(services: cmd.Services) -> None:
    log.info("scheduled sync starting")
    try:
        result = SyncVulnerabilitiesService(
            services.target_repo,
            services.vulnerability_repo,
            services.target_vulnerability_repo,
            services.sources,
        ).sync_all()
        log.info(
            "scheduled sync done targets=%d vulns=%d errors=%d",
            result.targets_processed,
            result.vulnerabilities_seen,
            len(result.errors),
        )
    except Exception:
        log.exception("scheduled sync failed")


async def _run_notify(services: cmd.Services, channel) -> None:
    log.info("scheduled notify starting")
    try:
        snapshot = ExportService(
            services.target_repo,
            services.vulnerability_repo,
            services.target_vulnerability_repo,
        ).snapshot()
    except Exception:
        log.exception("scheduled notify failed (snapshot)")
        return

    findings = group_findings(snapshot)
    summary = build_summary_message(
        report_date=datetime.now(timezone.utc).date(),
        targets_processed=len(services.target_repo.list_all()),
        new_findings=len(findings),
        errors=0,
    )
    await channel.send(content=summary)
    for finding in findings:
        await channel.send(embed=build_finding_embed(finding))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    env_path = Path(argv[0] if argv else ".env")
    try:
        config = load_config(env_path)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    client = build_client(config)
    client.run(config.discord_token)
    return 0
```

- [ ] **Step 4: Update `__main__.py`**

Replace `src/updater/__main__.py` with:

```python
from updater.presentation.discord_bot.bot import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the smoke test**

Run: `pytest tests/presentation/discord_bot/test_commands.py::test_bot_module_exposes_main_and_build_client -v`
Expected: PASS.

- [ ] **Step 6: Run the full test suite**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/updater/presentation/discord_bot/bot.py src/updater/__main__.py tests/presentation/discord_bot/test_commands.py
git commit -m "feat(bot): wire discord client, command tree, scheduler loop"
```

---

## Task 11: Remove the legacy CLI

**Files:**
- Delete: `src/updater/presentation/cli.py`
- Delete: `tests/presentation/test_cli.py`

- [ ] **Step 1: Delete the CLI module**

Run: `rm src/updater/presentation/cli.py tests/presentation/test_cli.py`

- [ ] **Step 2: Run the test suite**

Run: `pytest -q`
Expected: all PASS (no references remain).

- [ ] **Step 3: Grep to confirm no stragglers reference the deleted module**

Run: `grep -rn "presentation.cli" src tests`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "refactor: remove legacy CLI (replaced by discord bot)"
```

---

## Task 12: Update README and add `.env.example`

**Files:**
- Modify: `README.md`
- Create: `.env.example`

- [ ] **Step 1: Create `.env.example`**

`.env.example`:

```
DISCORD_TOKEN=your-bot-token-here
DISCORD_GUILD_ID=000000000000000000
DISCORD_CHANNEL_ID=000000000000000000
DISCORD_ADMIN_ROLE_ID=000000000000000000
SYNC_TIME=08:00
NOTIFY_TIME=09:00
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=pwn2own_updater
```

- [ ] **Step 2: Update `README.md`**

Replace any CLI usage section with a Discord bot section. At minimum the README should:

- Mention `pip install -e ".[dev]"`
- Mention copying `.env.example` to `.env` and filling values
- Mention running with `updater-bot`
- List the slash commands from the spec
- Note that read-only commands are open and other commands require the admin role

(Update the file's existing structure; do not introduce a new doc file.)

- [ ] **Step 3: Run the test suite once more**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md .env.example
git commit -m "docs: update README for discord bot, add .env.example"
```

---

## Verification

After all tasks, run:

```bash
pytest -q
```

Expected: all tests PASS.

```bash
updater-bot
```

Expected: with a valid `.env`, the bot logs `Bot ready. Commands synced to guild ...` and stays online. With a missing/invalid `.env`, it prints `config error: ...` to stderr and exits 2.

Manual smoke check (in Discord, after inviting the bot to the configured guild):

- `/list-targets` works for any user.
- `/add-target` requires the admin role.
- `/sync-cves` replies with an ephemeral message (visible only to the invoker).
- `/set-schedule 10:00 11:00` updates `.env` in place; `/show-schedule` reflects the new values.
- Wait until `SYNC_TIME`; the bot runs a sync silently. Wait until `NOTIFY_TIME`; the bot posts a summary + one embed per finding to the configured channel.
