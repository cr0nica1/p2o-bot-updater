# Vendor Firmware Discord Commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose existing vendor firmware config and lookup infrastructure through Discord bot commands, extend `/add-target` with `vendor_alias`, and return friendly "no firmware information" messages when vendor config is missing or mismatched.

**Architecture:** Reuse existing `VendorConfig` model, `VendorConfigRepository`, `FirmwareLookupService`, and `BrowserAdapter`. Add `vendor_config_repo` and `browser` to the Discord `Services` dataclass. Add six new command handlers in `commands.py` and register them in `bot.py`. All validation errors and missing configs surface as plain text results rather than exceptions.

**Tech Stack:** Python 3.12+, `discord.py`, pytest/pytest-asyncio, MongoDB, existing `CloakBrowserAdapter`.

---

## File Structure

- `src/updater/presentation/discord_bot/commands.py`
  - Extend `Services` with `vendor_config_repo` and `browser` fields.
  - Add `handle_set_vendor_firmware`, `handle_import_vendor_firmware`, `handle_set_vendor_alias`, `handle_lookup_firmware`.
  - Extend `handle_add_target` signature with `vendor_alias`.
- `src/updater/presentation/discord_bot/bot.py`
  - Register `/set-vendor-firmware`, `/import-vendor-firmware`, `/set-vendor-alias`, `/lookup-firmware` slash commands.
  - Extend `/add-target` registration with `vendor_alias` parameter.
  - Update `_build_services` to construct `MongoVendorConfigRepository` and `CloakBrowserAdapter`.
- `tests/presentation/discord_bot/test_commands.py`
  - Add `FakeVendorConfigRepo` and `FakeBrowserAdapter` test doubles.
  - Add tests for each new command handler and the extended `handle_add_target`.
- `src/updater/application/firmware_lookup.py`
  - No changes needed — existing service already handles all the logic.

No database schema changes needed. `vendor_configs` collection and `VendorConfig` model already exist.

---

### Task 1: Extend Services and Test Infrastructure

**Files:**
- Modify: `src/updater/presentation/discord_bot/commands.py:38-44`
- Modify: `tests/presentation/discord_bot/test_commands.py:82-120`

- [ ] **Step 1: Write the failing test**

Add `FakeVendorConfigRepo` and `FakeBrowserAdapter` to `tests/presentation/discord_bot/test_commands.py`, after `FakeLinkRepo` (after line 110), and update `_services()` helper to accept and pass the new fields:

```python
class FakeVendorConfigRepo:
    def __init__(self, configs=None):
        self.configs = {c.vendor: c for c in (configs or [])}

    def upsert(self, config):
        self.configs[config.vendor] = config
        return config

    def find_by_vendor(self, vendor):
        from updater.domain.models import normalize_name
        norm = normalize_name(vendor)
        return next((c for c in self.configs.values() if c.normalized_vendor == norm), None)

    def list_all(self):
        return list(self.configs.values())

    def delete(self, vendor):
        from updater.domain.models import normalize_name
        norm = normalize_name(vendor)
        for key in list(self.configs):
            if normalize_name(key) == norm:
                del self.configs[key]
                return True
        return False


class FakeBrowserAdapter:
    def __init__(self, html="<span>v1.0</span><a href='https://example.com/fw.bin'>download</a>"):
        self.html = html
        self.calls = []

    def fetch_element_html(self, url, element_id):
        self.calls.append({"url": url, "element_id": element_id})
        return self.html
```

Update `_services()` to accept and pass the new optional parameters:

```python
def _services(target_repo=None, vuln_repo=None, link_repo=None, version_repo=None, sources=None, vendor_config_repo=None, browser=None):
    return Services(
        target_repo=target_repo or FakeTargetRepo(),
        version_repo=version_repo or FakeVersionRepo(),
        vulnerability_repo=vuln_repo or FakeVulnRepo(),
        target_vulnerability_repo=link_repo or FakeLinkRepo(),
        sources=sources or [],
        vendor_config_repo=vendor_config_repo or FakeVendorConfigRepo(),
        browser=browser or FakeBrowserAdapter(),
    )
```

Add imports at the top of the test file:

```python
from updater.domain.models import Target, TargetVulnerability, VendorConfig, Vulnerability
```

(Only add `VendorConfig` if not already imported.)

Add a basic test to verify the new fields exist:

```python
def test_services_includes_vendor_config_repo_and_browser():
    services = _services()
    assert services.vendor_config_repo is not None
    assert services.browser is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_services_includes_vendor_config_repo_and_browser -v
```

Expected: FAIL with `TypeError: Services.__init__() got an unexpected keyword argument 'vendor_config_repo'` because `Services` does not have the new fields yet.

- [ ] **Step 3: Extend the Services dataclass**

In `src/updater/presentation/discord_bot/commands.py`, update the imports at the top to add `VendorConfigRepository` and `VendorConfig`:

```python
from updater.domain.repositories import (
    TargetRepository,
    TargetVersionRepository,
    TargetVulnerabilityRepository,
    VendorConfigRepository,
    VulnerabilityRepository,
    VulnerabilitySource,
)
```

Add a `BrowserAdapter` import from the application layer:

```python
from updater.application.firmware_lookup import BrowserAdapter
```

Extend the `Services` dataclass (currently at line 38):

```python
@dataclass
class Services:
    target_repo: TargetRepository
    version_repo: TargetVersionRepository
    vulnerability_repo: VulnerabilityRepository
    target_vulnerability_repo: TargetVulnerabilityRepository
    sources: list[VulnerabilitySource]
    vendor_config_repo: VendorConfigRepository
    browser: BrowserAdapter
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_services_includes_vendor_config_repo_and_browser -v
```

Expected: PASS.

- [ ] **Step 5: Run existing tests to verify no regressions**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py -v
```

Expected: All existing tests still pass. Any test using `_services()` now gets the default fake repos automatically.

- [ ] **Step 6: Update bot.py `_build_services`**

In `src/updater/presentation/discord_bot/bot.py`, add imports:

```python
from updater.infrastructure.mongo import (
    MongoDatabase,
    MongoTargetRepository,
    MongoTargetVersionRepository,
    MongoTargetVulnerabilityRepository,
    MongoVendorConfigRepository,
    MongoVulnerabilityRepository,
)
from updater.infrastructure.browser.cloak import CloakBrowserAdapter
```

Update `_build_services` to include the new fields:

```python
def _build_services(config: BotConfig) -> cmd.Services:
    db = MongoDatabase(uri=config.mongodb_uri, database=config.mongodb_database)
    return cmd.Services(
        target_repo=MongoTargetRepository(db.db),
        version_repo=MongoTargetVersionRepository(db.db),
        vulnerability_repo=MongoVulnerabilityRepository(db.db),
        target_vulnerability_repo=MongoTargetVulnerabilityRepository(db.db),
        sources=[NvdSource(), ZdiSource()],
        vendor_config_repo=MongoVendorConfigRepository(db.db),
        browser=CloakBrowserAdapter(),
    )
```

- [ ] **Step 7: Run full test suite**

Run:

```bash
pytest -q
```

Expected: All tests pass (existing tests use fake repos; bot.py `_build_services` is integration-level and not exercised by unit tests).

---

### Task 2: Add `/set-vendor-firmware` Command

**Files:**
- Modify: `src/updater/presentation/discord_bot/commands.py`
- Modify: `src/updater/presentation/discord_bot/bot.py`
- Modify: `tests/presentation/discord_bot/test_commands.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/presentation/discord_bot/test_commands.py`:

```python
async def test_set_vendor_firmware_creates_config():
    services = _services()
    result = await handle_set_vendor_firmware(
        services,
        vendor="Canon",
        url_template="https://example.com/{alias}/firmware",
        attr_id="downloads",
        regex=r"(v[\d.]+).*(https://[^\"']+)",
    )
    assert "Canon" in result.text
    saved = services.vendor_config_repo.find_by_vendor("Canon")
    assert saved is not None
    assert saved.url_template == "https://example.com/{alias}/firmware"


async def test_set_vendor_firmware_rejects_invalid_regex():
    services = _services()
    result = await handle_set_vendor_firmware(
        services,
        vendor="Canon",
        url_template="https://example.com/{alias}/firmware",
        attr_id="downloads",
        regex="[invalid(",
    )
    assert "invalid" in result.text.lower()


async def test_set_vendor_firmware_rejects_missing_alias_placeholder():
    services = _services()
    result = await handle_set_vendor_firmware(
        services,
        vendor="Canon",
        url_template="https://example.com/firmware",
        attr_id="downloads",
        regex=r"(v[\d.]+).*(https://[^\"']+)",
    )
    assert "{alias}" in result.text
```

Add `handle_set_vendor_firmware` to the test file's import block at the top:

```python
from updater.presentation.discord_bot.commands import (
    CommandResult,
    Services,
    handle_add_target,
    handle_add_vuln,
    handle_clear_database,
    handle_import_targets,
    handle_list_targets,
    handle_lookup_firmware,
    handle_remove_target,
    handle_search_vulns,
    handle_set_schedule,
    handle_set_vendor_alias,
    handle_set_vendor_firmware,
    handle_show_schedule,
    handle_show_target,
    handle_sync_cves,
)
```

(This import block will grow as we add handlers. Include all new handlers from all tasks now to avoid editing it repeatedly.)

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_set_vendor_firmware_creates_config tests/presentation/discord_bot/test_commands.py::test_set_vendor_firmware_rejects_invalid_regex tests/presentation/discord_bot/test_commands.py::test_set_vendor_firmware_rejects_missing_alias_placeholder -v
```

Expected: FAIL with `ImportError: cannot import name 'handle_set_vendor_firmware'`.

- [ ] **Step 3: Implement the handler**

Add to `src/updater/presentation/discord_bot/commands.py`:

```python
from updater.application.firmware_lookup import (
    BrowserAdapter,
    FirmwareLookupError,
    FirmwareLookupService,
    validate_vendor_inputs,
)
from updater.domain.models import Target, TargetVulnerability, VendorConfig, Vulnerability
```

Add the handler function (place it near the other admin command handlers, after `handle_add_vuln`):

```python
async def handle_set_vendor_firmware(
    services: Services,
    *,
    vendor: str,
    url_template: str,
    attr_id: str,
    regex: str,
) -> CommandResult:
    try:
        validate_vendor_inputs(url_template, regex)
    except FirmwareLookupError as exc:
        return CommandResult(text=str(exc), ephemeral=True)
    config = VendorConfig(
        vendor=vendor,
        url_template=url_template,
        attr_id=attr_id,
        regex=regex,
    )
    services.vendor_config_repo.upsert(config)
    return CommandResult(text=f"Vendor firmware config saved: {vendor}")
```

- [ ] **Step 4: Register the command in bot.py**

Add after the `add-vuln` command registration in `build_client()`:

```python
    @tree.command(name="set-vendor-firmware", description="Set vendor firmware lookup config", guild=guild)
    @app_commands.describe(
        vendor="Vendor name",
        url_template="HTTPS URL with {alias} placeholder",
        attr_id="HTML element ID to scrape",
        regex="Regex with 2+ groups (version, download URL)",
    )
    async def set_vendor_firmware(
        interaction: discord.Interaction,
        vendor: str,
        url_template: str,
        attr_id: str,
        regex: str,
    ):
        if not await _admin_only(interaction):
            return
        await _reply(
            interaction,
            await cmd.handle_set_vendor_firmware(
                services, vendor=vendor, url_template=url_template, attr_id=attr_id, regex=regex
            ),
        )
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_set_vendor_firmware_creates_config tests/presentation/discord_bot/test_commands.py::test_set_vendor_firmware_rejects_invalid_regex tests/presentation/discord_bot/test_commands.py::test_set_vendor_firmware_rejects_missing_alias_placeholder -v
```

Expected: PASS.

---

### Task 3: Add `/import-vendor-firmware` Command

**Files:**
- Modify: `src/updater/presentation/discord_bot/commands.py`
- Modify: `src/updater/presentation/discord_bot/bot.py`
- Modify: `tests/presentation/discord_bot/test_commands.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/presentation/discord_bot/test_commands.py`:

```python
async def test_import_vendor_firmware_imports_csv():
    csv_data = (
        "vendor,url_template,attr_id,regex\n"
        "Canon,https://example.com/{alias}/fw,downloads,(v[\\d.]+).*(https://[^\"']+)\n"
        "TP-Link,https://tplink.com/{alias}/fw,content,(v[\\d.]+).*(https://[^\"']+)\n"
    ).encode()
    services = _services()
    result = await handle_import_vendor_firmware(services, csv_bytes=csv_data)
    assert "2" in result.text
    assert services.vendor_config_repo.find_by_vendor("Canon") is not None
    assert services.vendor_config_repo.find_by_vendor("TP-Link") is not None


async def test_import_vendor_firmware_reports_invalid_rows():
    csv_data = (
        "vendor,url_template,attr_id,regex\n"
        "Canon,https://example.com/{alias}/fw,downloads,(v[\\d.]+).*(https://[^\"']+)\n"
        "BadVendor,http://no-alias.com/fw,downloads,(bad\n"
    ).encode()
    services = _services()
    result = await handle_import_vendor_firmware(services, csv_bytes=csv_data)
    assert "1" in result.text
    assert services.vendor_config_repo.find_by_vendor("Canon") is not None
    assert "BadVendor" in result.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_import_vendor_firmware_imports_csv tests/presentation/discord_bot/test_commands.py::test_import_vendor_firmware_reports_invalid_rows -v
```

Expected: FAIL with `ImportError: cannot import name 'handle_import_vendor_firmware'`.

- [ ] **Step 3: Implement the handler**

Add to `src/updater/presentation/discord_bot/commands.py`. Place this import near the top with the other standard library imports:

```python
import csv
import io
```

Add the handler:

```python
async def handle_import_vendor_firmware(
    services: Services,
    *,
    csv_bytes: bytes,
) -> CommandResult:
    text = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    saved = 0
    errors: list[str] = []
    for row in reader:
        vendor = row.get("vendor", "").strip()
        url_template = row.get("url_template", "").strip()
        attr_id = row.get("attr_id", "").strip()
        regex = row.get("regex", "").strip()
        if not all([vendor, url_template, attr_id, regex]):
            errors.append(f"Row skipped (missing fields): {vendor or '<empty>'}")
            continue
        try:
            validate_vendor_inputs(url_template, regex)
        except FirmwareLookupError as exc:
            errors.append(f"{vendor}: {exc}")
            continue
        config = VendorConfig(
            vendor=vendor,
            url_template=url_template,
            attr_id=attr_id,
            regex=regex,
        )
        services.vendor_config_repo.upsert(config)
        saved += 1
    lines = [f"Imported {saved} vendor firmware config(s)."]
    if errors:
        lines.append(f"Errors ({len(errors)}):")
        lines.extend(f"  - {e}" for e in errors)
    return CommandResult(text="\n".join(lines))
```

- [ ] **Step 4: Register the command in bot.py**

Add after the `set-vendor-firmware` registration:

```python
    @tree.command(name="import-vendor-firmware", description="Import vendor firmware configs from CSV", guild=guild)
    async def import_vendor_firmware(interaction: discord.Interaction, file: discord.Attachment):
        if not await _admin_only(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        data = await file.read()
        result = await cmd.handle_import_vendor_firmware(services, csv_bytes=data)
        await interaction.followup.send(content=result.text, ephemeral=True)
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_import_vendor_firmware_imports_csv tests/presentation/discord_bot/test_commands.py::test_import_vendor_firmware_reports_invalid_rows -v
```

Expected: PASS.

---

### Task 4: Add `/set-vendor-alias` Command

**Files:**
- Modify: `src/updater/presentation/discord_bot/commands.py`
- Modify: `src/updater/presentation/discord_bot/bot.py`
- Modify: `tests/presentation/discord_bot/test_commands.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/presentation/discord_bot/test_commands.py`:

```python
async def test_set_vendor_alias_updates_target():
    target = Target(id="t1", name="Canon MF654Cdw", vendor="Canon")
    services = _services(target_repo=FakeTargetRepo([target]))
    result = await handle_set_vendor_alias(services, target_id=1, vendor_alias="canon-mf654cdw")
    assert "canon-mf654cdw" in result.text
    updated = services.target_repo.find_by_name("Canon MF654Cdw")
    assert updated.vendor_alias == "canon-mf654cdw"


async def test_set_vendor_alias_rejects_invalid_target_id():
    services = _services()
    result = await handle_set_vendor_alias(services, target_id=1, vendor_alias="test")
    assert "Invalid target ID" in result.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_set_vendor_alias_updates_target tests/presentation/discord_bot/test_commands.py::test_set_vendor_alias_rejects_invalid_target_id -v
```

Expected: FAIL with `ImportError: cannot import name 'handle_set_vendor_alias'`.

- [ ] **Step 3: Implement the handler**

Add to `src/updater/presentation/discord_bot/commands.py`:

```python
async def handle_set_vendor_alias(
    services: Services,
    *,
    target_id: int,
    vendor_alias: str,
) -> CommandResult:
    targets = _sorted_targets(services)
    if target_id < 1 or target_id > len(targets):
        return CommandResult(
            text=f"Invalid target ID. Use /list-targets to see available targets (1-{len(targets)}).",
            ephemeral=True,
        )
    target = targets[target_id - 1]
    target.vendor_alias = vendor_alias
    services.target_repo.upsert(target)
    return CommandResult(text=f"Vendor alias set: {target.name} → {vendor_alias}")
```

- [ ] **Step 4: Register the command in bot.py**

Add after the `set-vendor-firmware` registration:

```python
    @tree.command(name="set-vendor-alias", description="Set vendor alias for firmware lookup", guild=guild)
    @app_commands.describe(
        target_id="Target number from /list-targets",
        vendor_alias="URL path segment for vendor firmware page",
    )
    async def set_vendor_alias(
        interaction: discord.Interaction,
        target_id: int,
        vendor_alias: str,
    ):
        if not await _admin_only(interaction):
            return
        await _reply(
            interaction,
            await cmd.handle_set_vendor_alias(services, target_id=target_id, vendor_alias=vendor_alias),
        )
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_set_vendor_alias_updates_target tests/presentation/discord_bot/test_commands.py::test_set_vendor_alias_rejects_invalid_target_id -v
```

Expected: PASS.

---

### Task 5: Extend `/add-target` with `vendor_alias`

**Files:**
- Modify: `src/updater/presentation/discord_bot/commands.py:222-237`
- Modify: `src/updater/presentation/discord_bot/bot.py:147-169`
- Modify: `tests/presentation/discord_bot/test_commands.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/presentation/discord_bot/test_commands.py`:

```python
async def test_add_target_accepts_vendor_alias():
    services = _services()
    result = await handle_add_target(
        services,
        name="Canon MF654Cdw",
        vendor="Canon",
        vendor_alias="canon-mf654cdw",
    )
    assert "Canon MF654Cdw" in result.text
    target = services.target_repo.find_by_name("Canon MF654Cdw")
    assert target.vendor_alias == "canon-mf654cdw"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_add_target_accepts_vendor_alias -v
```

Expected: FAIL with `TypeError: handle_add_target() got an unexpected keyword argument 'vendor_alias'`.

- [ ] **Step 3: Update the handler signature**

In `src/updater/presentation/discord_bot/commands.py`, update `handle_add_target`:

```python
async def handle_add_target(
    services: Services,
    *,
    name: str,
    aliases: list[str] | None = None,
    vendor: str | None = None,
    vendor_alias: str | None = None,
    category: str | None = None,
) -> CommandResult:
    target = Target(
        name=name,
        aliases=list(aliases or []),
        vendor=vendor,
        vendor_alias=vendor_alias,
        category=category,
    )
    services.target_repo.upsert(target)
    return CommandResult(text=f"Added target: {name}")
```

- [ ] **Step 4: Update bot.py command registration**

In `src/updater/presentation/discord_bot/bot.py`, update the `add-target` command:

```python
    @tree.command(name="add-target", description="Add a target", guild=guild)
    @app_commands.describe(
        name="Target name",
        aliases="Semicolon-separated aliases",
        vendor="Vendor",
        vendor_alias="URL path segment for firmware lookup",
        category="Category",
    )
    async def add_target(
        interaction: discord.Interaction,
        name: str,
        aliases: str | None = None,
        vendor: str | None = None,
        vendor_alias: str | None = None,
        category: str | None = None,
    ):
        if not await _admin_only(interaction):
            return
        alias_list = [a.strip() for a in (aliases or "").split(";") if a.strip()]
        await _reply(
            interaction,
            await cmd.handle_add_target(
                services, name=name, aliases=alias_list, vendor=vendor, vendor_alias=vendor_alias, category=category
            ),
        )
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py::test_add_target_accepts_vendor_alias -v
```

Expected: PASS.

- [ ] **Step 6: Run all add-target tests**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py -k "add_target" -v
```

Expected: All add-target tests pass.

---

### Task 6: Add `/lookup-firmware` Command

**Files:**
- Modify: `src/updater/presentation/discord_bot/commands.py`
- Modify: `src/updater/presentation/discord_bot/bot.py`
- Modify: `tests/presentation/discord_bot/test_commands.py`

- [ ] **Step 1: Write the failing test for stored config lookup**

Append to `tests/presentation/discord_bot/test_commands.py`:

```python
async def test_lookup_firmware_uses_stored_vendor_config():
    target = Target(id="t1", name="Canon MF654Cdw", vendor="Canon", vendor_alias="canon-mf654cdw")
    config = VendorConfig(
        vendor="Canon",
        url_template="https://example.com/{alias}/fw",
        attr_id="downloads",
        regex=r"version:([\d.]+).*href=[\"']([^\"']+)",
    )
    browser = FakeBrowserAdapter(html='version:2.1.0 <a href="https://example.com/fw.bin">download</a>')
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vendor_config_repo=FakeVendorConfigRepo([config]),
        browser=browser,
    )
    result = await handle_lookup_firmware(services, target_id=1)
    assert "Canon MF654Cdw" in result.text
    assert "2.1.0" in result.text
    assert "https://example.com/fw.bin" in result.text


async def test_lookup_firmware_returns_no_info_when_no_vendor():
    target = Target(id="t1", name="Some Target")
    services = _services(target_repo=FakeTargetRepo([target]))
    result = await handle_lookup_firmware(services, target_id=1)
    assert "No firmware information" in result.text


async def test_lookup_firmware_returns_no_info_when_no_vendor_alias():
    target = Target(id="t1", name="Canon MF654Cdw", vendor="Canon")
    services = _services(target_repo=FakeTargetRepo([target]))
    result = await handle_lookup_firmware(services, target_id=1)
    assert "No firmware information" in result.text


async def test_lookup_firmware_returns_no_info_when_no_config():
    target = Target(id="t1", name="Canon MF654Cdw", vendor="Canon", vendor_alias="canon-mf654cdw")
    services = _services(target_repo=FakeTargetRepo([target]))
    result = await handle_lookup_firmware(services, target_id=1)
    assert "No firmware information" in result.text


async def test_lookup_firmware_returns_no_info_on_lookup_error():
    target = Target(id="t1", name="Canon MF654Cdw", vendor="Canon", vendor_alias="canon-mf654cdw")
    config = VendorConfig(
        vendor="Canon",
        url_template="https://example.com/{alias}/fw",
        attr_id="downloads",
        regex=r"version:([\d.]+).*href=[\"']([^\"']+)",
    )
    browser = FakeBrowserAdapter(html="<p>no match</p>")
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vendor_config_repo=FakeVendorConfigRepo([config]),
        browser=browser,
    )
    result = await handle_lookup_firmware(services, target_id=1)
    assert "No firmware information" in result.text


async def test_lookup_firmware_with_runtime_inputs():
    target = Target(id="t1", name="Canon MF654Cdw", vendor="Canon", vendor_alias="canon-mf654cdw")
    browser = FakeBrowserAdapter(html='version:3.0.0 <a href="https://example.com/fw3.bin">download</a>')
    services = _services(
        target_repo=FakeTargetRepo([target]),
        browser=browser,
    )
    result = await handle_lookup_firmware(
        services,
        target_id=1,
        url_template="https://example.com/{alias}/fw",
        attr_id="downloads",
        regex=r"version:([\d.]+).*href=[\"']([^\"']+)",
    )
    assert "3.0.0" in result.text
    assert "fw3.bin" in result.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py -k "lookup_firmware" -v
```

Expected: FAIL with `ImportError: cannot import name 'handle_lookup_firmware'`.

- [ ] **Step 3: Implement the handler**

Add to `src/updater/presentation/discord_bot/commands.py`:

```python
async def handle_lookup_firmware(
    services: Services,
    *,
    target_id: int,
    url_template: str | None = None,
    attr_id: str | None = None,
    regex: str | None = None,
) -> CommandResult:
    targets = _sorted_targets(services)
    if target_id < 1 or target_id > len(targets):
        return CommandResult(
            text=f"Invalid target ID. Use /list-targets to see available targets (1-{len(targets)}).",
            ephemeral=True,
        )
    target = targets[target_id - 1]

    lookup = FirmwareLookupService(
        services.target_repo,
        services.vendor_config_repo,
        services.browser,
    )

    runtime_inputs = all([url_template, attr_id, regex])
    try:
        if runtime_inputs:
            result = await asyncio.to_thread(
                lookup.lookup_with_inputs,
                target_id,
                url_template,
                attr_id,
                regex,
            )
        else:
            result = await asyncio.to_thread(lookup.lookup, target_id)
    except Exception:
        return CommandResult(
            text=f"No firmware information found for {target.name}.",
            ephemeral=True,
        )

    lines = [
        f"Firmware lookup: {result.target_name}",
        f"Vendor: {result.vendor}",
        f"URL: {result.resolved_url}",
        f"Version: {result.version}",
        f"Download: {result.download_url}",
    ]
    return CommandResult(text="\n".join(lines))
```

- [ ] **Step 4: Register the command in bot.py**

Add after the `set-vendor-alias` registration:

```python
    @tree.command(name="lookup-firmware", description="Look up firmware version for a target", guild=guild)
    @app_commands.describe(
        target_id="Target number from /list-targets",
        url_template="Optional: override stored URL template",
        attr_id="Optional: override stored element ID",
        regex="Optional: override stored regex",
    )
    async def lookup_firmware(
        interaction: discord.Interaction,
        target_id: int,
        url_template: str | None = None,
        attr_id: str | None = None,
        regex: str | None = None,
    ):
        await _reply(
            interaction,
            await cmd.handle_lookup_firmware(
                services, target_id=target_id, url_template=url_template, attr_id=attr_id, regex=regex
            ),
        )
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/presentation/discord_bot/test_commands.py -k "lookup_firmware" -v
```

Expected: PASS.

---

### Task 7: Final Verification

**Files:**
- Test only: no source changes expected.

- [ ] **Step 1: Run targeted Discord bot tests**

Run:

```bash
pytest tests/presentation/discord_bot/ -v
```

Expected: PASS.

- [ ] **Step 2: Run the full test suite**

Run:

```bash
pytest -q
```

Expected: PASS.

- [ ] **Step 3: Inspect changed files**

Run:

```bash
git diff --stat
```

Expected: Changes only in `commands.py`, `bot.py`, and `test_commands.py`.

---

## Self-Review

- Spec coverage: `/set-vendor-firmware` (Task 2), `/import-vendor-firmware` (Task 3), `/set-vendor-alias` (Task 4), `/add-target` extension (Task 5), `/lookup-firmware` with stored + runtime inputs (Task 6), friendly "no firmware information" on all failure paths (Task 6 tests), Services extension (Task 1). All requirements covered.
- Placeholder scan: No TBD/TODO/fill-in placeholders. All steps contain complete code.
- Type consistency: `Services` fields `vendor_config_repo: VendorConfigRepository` and `browser: BrowserAdapter` are consistent across Tasks 1-6. `handle_lookup_firmware` uses `FirmwareLookupService` from the existing application layer. `VendorConfig` model fields `vendor`, `url_template`, `attr_id`, `regex` match across all tasks.
