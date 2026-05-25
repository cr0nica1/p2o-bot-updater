# Firmware Lookup Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI prototype that resolves an existing target by `/list-targets` ID, uses a per-target vendor alias plus per-vendor crawler configuration, and returns the newest firmware version and download URL from a vendor page.

**Architecture:** Extend the existing domain/application/infrastructure split. Add `VendorConfig` storage beside existing Mongo repositories, keep crawler behavior behind a small browser adapter protocol, and expose the prototype through CLI scripts rather than Discord commands.

**Tech Stack:** Python 3.10+, dataclasses, Protocol repositories, MongoDB/PyMongo, CSV import, argparse CLI, Playwright with optional CloakBrowser integration boundary, pytest.

---

## File Structure

Create or modify these files:

- Modify: `src/updater/domain/models.py`
  - Add `Target.vendor_alias`.
  - Add `VendorConfig` dataclass.
- Modify: `src/updater/domain/repositories.py`
  - Add `VendorConfigRepository` protocol.
- Modify: `src/updater/infrastructure/csv_loader.py`
  - Treat `vendor_alias` as a known CSV column.
  - Load it into `Target.vendor_alias`.
- Modify: `src/updater/infrastructure/mongo.py`
  - Persist `Target.vendor_alias`.
  - Add `vendor_config_to_document`, `vendor_config_from_document`, and `MongoVendorConfigRepository`.
  - Add a unique `normalized_vendor` index on `vendor_configs`.
- Create: `src/updater/application/firmware_lookup.py`
  - Add validation helpers, result dataclass, browser protocol, and `FirmwareLookupService`.
- Create: `src/updater/infrastructure/browser/__init__.py`
  - Export browser adapter implementation.
- Create: `src/updater/infrastructure/browser/cloak.py`
  - Implement `CloakBrowserAdapter` behind the service protocol.
- Create: `src/updater/cli/__init__.py`
  - Package marker for CLI modules.
- Create: `src/updater/cli/firmware_lookup.py`
  - Implement `firmware-lookup` CLI.
- Create: `src/updater/cli/vendor_config.py`
  - Implement `vendor-config` CLI.
- Modify: `pyproject.toml`
  - Add `playwright` dependency.
  - Add console scripts.
- Modify: `README.md`
  - Document the prototype CLI usage and CSV `vendor_alias` column.
- Modify: `tests/domain/test_models.py`
  - Add target/vendor config model tests.
- Modify: `tests/infrastructure/test_csv_loader.py`
  - Add CSV test for `vendor_alias`.
- Modify: `tests/infrastructure/test_mongo_mapping.py`
  - Add mapping/repository tests for `vendor_alias` and `VendorConfig`.
- Create: `tests/application/test_firmware_lookup.py`
  - Add service tests with fake repositories and fake browser adapter.
- Create: `tests/cli/test_vendor_config_cli.py`
  - Add CLI tests for config validation and output.
- Create: `tests/cli/test_firmware_lookup_cli.py`
  - Add CLI tests for lookup output using patched services.

---

### Task 1: Add target vendor aliases and vendor config domain model

**Files:**
- Modify: `src/updater/domain/models.py`
- Modify: `src/updater/domain/repositories.py`
- Modify: `tests/domain/test_models.py`

- [ ] **Step 1: Write failing domain tests**

Append these tests to `tests/domain/test_models.py`:

```python
from updater.domain.models import Target, VendorConfig


def test_target_stores_vendor_alias():
    target = Target(name="Canon MF654Cdw", vendor="Canon", vendor_alias="mf654cdw")

    assert target.vendor_alias == "mf654cdw"


def test_vendor_config_stores_crawler_settings():
    config = VendorConfig(
        vendor="Canon",
        url_template="https://vendor.example/downloads/{alias}/firmware",
        attr_id="firmware",
        regex=r"Version ([^<]+).*href=\"([^\"]+)\"",
    )

    assert config.vendor == "Canon"
    assert config.normalized_vendor == "canon"
    assert config.url_template == "https://vendor.example/downloads/{alias}/firmware"
    assert config.attr_id == "firmware"
    assert config.regex == r"Version ([^<]+).*href=\"([^\"]+)\""
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/domain/test_models.py -q
```

Expected: FAIL because `Target` does not accept `vendor_alias` and `VendorConfig` does not exist.

- [ ] **Step 3: Add domain model fields**

In `src/updater/domain/models.py`, update the `Target` dataclass to include `vendor_alias` after `vendor`:

```python
@dataclass
class Target:
    name: str
    aliases: list[str] = field(default_factory=list)
    vendor: str | None = None
    vendor_alias: str | None = None
    category: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
```

In the same file, add `VendorConfig` after `TargetVersion`:

```python
@dataclass
class VendorConfig:
    vendor: str
    url_template: str
    attr_id: str
    regex: str
    id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def normalized_vendor(self) -> str:
        return normalize_name(self.vendor)
```

- [ ] **Step 4: Add repository protocol**

In `src/updater/domain/repositories.py`, update the import:

```python
from updater.domain.models import Target, TargetVersion, TargetVulnerability, VendorConfig, Vulnerability
```

Add this protocol after `TargetVersionRepository`:

```python
class VendorConfigRepository(Protocol):
    def upsert(self, config: VendorConfig) -> VendorConfig: ...
    def find_by_vendor(self, vendor: str) -> VendorConfig | None: ...
    def list_all(self) -> list[VendorConfig]: ...
    def delete(self, vendor: str) -> bool: ...
```

- [ ] **Step 5: Run domain tests**

Run:

```bash
pytest tests/domain/test_models.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/updater/domain/models.py src/updater/domain/repositories.py tests/domain/test_models.py
git commit -m "feat: add firmware vendor config domain model"
```

---

### Task 2: Persist vendor aliases in CSV and Mongo mappings

**Files:**
- Modify: `src/updater/infrastructure/csv_loader.py`
- Modify: `src/updater/infrastructure/mongo.py`
- Modify: `tests/infrastructure/test_csv_loader.py`
- Modify: `tests/infrastructure/test_mongo_mapping.py`

- [ ] **Step 1: Write failing CSV loader test**

Append to `tests/infrastructure/test_csv_loader.py`:

```python

def test_loads_vendor_alias_as_known_target_field(tmp_path: Path):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text(
        "name,vendor,vendor_alias,notes\n"
        "Canon MF654Cdw,Canon,mf654cdw,contest target\n",
        encoding="utf-8",
    )

    rows = CsvTargetLoader().load(csv_path)

    assert rows.errors == []
    assert rows.items[0].target.vendor_alias == "mf654cdw"
    assert rows.items[0].target.raw_metadata == {"notes": "contest target"}
```

- [ ] **Step 2: Write failing Mongo mapping tests**

Update the import at the top of `tests/infrastructure/test_mongo_mapping.py`:

```python
from updater.domain.models import Target, TargetVulnerability, VendorConfig, Vulnerability
```

Update the infrastructure import to include new helpers and repo:

```python
from updater.infrastructure.mongo import (
    MongoTargetRepository,
    MongoTargetVersionRepository,
    MongoTargetVulnerabilityRepository,
    MongoVendorConfigRepository,
    MongoVulnerabilityRepository,
    target_from_document,
    target_to_document,
    target_vulnerability_to_document,
    vendor_config_from_document,
    vendor_config_to_document,
    vulnerability_to_document,
)
```

Append these tests:

```python

def test_target_document_contains_vendor_alias():
    target = Target(name="Canon MF654Cdw", vendor="Canon", vendor_alias="mf654cdw")

    document = target_to_document(target)
    restored = target_from_document(
        {
            "_id": "target-1",
            **document,
            "created_at": target.created_at,
            "updated_at": target.updated_at,
        }
    )

    assert document["vendor_alias"] == "mf654cdw"
    assert restored.vendor_alias == "mf654cdw"


def test_vendor_config_document_contains_normalized_vendor():
    config = VendorConfig(
        vendor=" Canon ",
        url_template="https://vendor.example/{alias}",
        attr_id="firmware",
        regex=r"Version ([^<]+).*href=\"([^\"]+)\"",
    )

    document = vendor_config_to_document(config)

    assert document["vendor"] == " Canon "
    assert document["normalized_vendor"] == "canon"
    assert document["url_template"] == "https://vendor.example/{alias}"
    assert document["attr_id"] == "firmware"
    assert document["regex"] == r"Version ([^<]+).*href=\"([^\"]+)\""


def test_vendor_config_from_document_restores_model():
    config = VendorConfig(
        vendor="Canon",
        url_template="https://vendor.example/{alias}",
        attr_id="firmware",
        regex="Version (.+) (.+)",
    )
    document = {
        "_id": "config-1",
        **vendor_config_to_document(config),
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }

    restored = vendor_config_from_document(document)

    assert restored.id == "config-1"
    assert restored.vendor == "Canon"
    assert restored.normalized_vendor == "canon"


def test_vendor_config_repository_delete_returns_true_when_match_found():
    class FakeCollection:
        def __init__(self):
            self.last_filter = None

        def delete_one(self, filter):
            self.last_filter = filter

            class Result:
                deleted_count = 1

            return Result()

    collection = FakeCollection()
    repo = MongoVendorConfigRepository.__new__(MongoVendorConfigRepository)
    repo.collection = collection

    deleted = repo.delete(" Canon ")

    assert deleted is True
    assert collection.last_filter == {"normalized_vendor": "canon"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest tests/infrastructure/test_csv_loader.py tests/infrastructure/test_mongo_mapping.py -q
```

Expected: FAIL because `vendor_alias` is not loaded or persisted and vendor config mapping does not exist.

- [ ] **Step 4: Update CSV loader**

In `src/updater/infrastructure/csv_loader.py`, add `vendor_alias` to `KNOWN_COLUMNS`:

```python
KNOWN_COLUMNS = {
    "name",
    "aliases",
    "vendor",
    "vendor_alias",
    "category",
    "version",
    "version_type",
    "release_date",
    "source_url",
}
```

Update target construction in `CsvTargetLoader.load()`:

```python
target = Target(
    name=name,
    aliases=_split_aliases(row.get("aliases")),
    vendor=_clean_optional(row.get("vendor")),
    vendor_alias=_clean_optional(row.get("vendor_alias")),
    category=_clean_optional(row.get("category")),
    raw_metadata=_unknown_metadata(row),
)
```

- [ ] **Step 5: Update Mongo mappings and repository**

In `src/updater/infrastructure/mongo.py`, add `VendorConfig` to the model import:

```python
from updater.domain.models import (
    Target,
    TargetVersion,
    TargetVulnerability,
    VendorConfig,
    Vulnerability,
    normalize_name,
)
```

Update `target_to_document()`:

```python
def target_to_document(target: Target) -> dict[str, Any]:
    return {
        "name": target.name,
        "normalized_name": target.normalized_name,
        "aliases": list(target.aliases),
        "vendor": target.vendor,
        "vendor_alias": target.vendor_alias,
        "category": target.category,
        "raw_metadata": dict(target.raw_metadata),
        "created_at": target.created_at,
        "updated_at": target.updated_at,
    }
```

Update `target_from_document()`:

```python
def target_from_document(document: dict[str, Any]) -> Target:
    return Target(
        id=_document_id(document),
        name=document["name"],
        aliases=list(document.get("aliases", [])),
        vendor=document.get("vendor"),
        vendor_alias=document.get("vendor_alias"),
        category=document.get("category"),
        raw_metadata=dict(document.get("raw_metadata", {})),
        created_at=document["created_at"],
        updated_at=document["updated_at"],
    )
```

Add these helpers after `target_version_from_document()`:

```python
def vendor_config_to_document(config: VendorConfig) -> dict[str, Any]:
    return {
        "vendor": config.vendor,
        "normalized_vendor": config.normalized_vendor,
        "url_template": config.url_template,
        "attr_id": config.attr_id,
        "regex": config.regex,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


def vendor_config_from_document(document: dict[str, Any]) -> VendorConfig:
    return VendorConfig(
        id=_document_id(document),
        vendor=document["vendor"],
        url_template=document["url_template"],
        attr_id=document["attr_id"],
        regex=document["regex"],
        created_at=document["created_at"],
        updated_at=document["updated_at"],
    )
```

Update `MongoDatabase.ensure_indexes()`:

```python
self.db.vendor_configs.create_index("normalized_vendor", unique=True)
```

Add this repository class after `MongoTargetVersionRepository`:

```python
class MongoVendorConfigRepository:
    def __init__(self, db: Any) -> None:
        self.collection = _as_collection(db, "vendor_configs")

    def upsert(self, config: VendorConfig) -> VendorConfig:
        document = vendor_config_to_document(config)
        created_at = document.pop("created_at")
        updated = self.collection.find_one_and_update(
            {"normalized_vendor": document["normalized_vendor"]},
            {"$set": document, "$setOnInsert": {"created_at": created_at}},
            upsert=True,
            return_document=_return_document_after(),
        )
        return vendor_config_from_document(updated)

    def find_by_vendor(self, vendor: str) -> VendorConfig | None:
        document = self.collection.find_one({"normalized_vendor": normalize_name(vendor)})
        return vendor_config_from_document(document) if document else None

    def list_all(self) -> list[VendorConfig]:
        return [vendor_config_from_document(document) for document in self.collection.find().sort("normalized_vendor", ASCENDING)]

    def delete(self, vendor: str) -> bool:
        result = self.collection.delete_one({"normalized_vendor": normalize_name(vendor)})
        return result.deleted_count > 0
```

- [ ] **Step 6: Run infrastructure tests**

Run:

```bash
pytest tests/infrastructure/test_csv_loader.py tests/infrastructure/test_mongo_mapping.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/updater/infrastructure/csv_loader.py src/updater/infrastructure/mongo.py tests/infrastructure/test_csv_loader.py tests/infrastructure/test_mongo_mapping.py
git commit -m "feat: persist firmware vendor aliases and configs"
```

---

### Task 3: Implement firmware lookup service with fake browser tests

**Files:**
- Create: `src/updater/application/firmware_lookup.py`
- Create: `tests/application/test_firmware_lookup.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/application/test_firmware_lookup.py`:

```python
import pytest

from updater.application.firmware_lookup import (
    FirmwareLookupError,
    FirmwareLookupService,
    validate_vendor_config,
)
from updater.domain.models import Target, VendorConfig


class FakeTargetRepository:
    def __init__(self, targets):
        self.targets = list(targets)

    def list_all(self):
        return list(self.targets)


class FakeVendorConfigRepository:
    def __init__(self, configs):
        self.configs = {config.normalized_vendor: config for config in configs}

    def find_by_vendor(self, vendor):
        from updater.domain.models import normalize_name

        return self.configs.get(normalize_name(vendor))


class FakeBrowser:
    def __init__(self, html):
        self.html = html
        self.calls = []

    def fetch_element_html(self, url, element_id):
        self.calls.append((url, element_id))
        return self.html


def _service(targets, configs, html):
    return FirmwareLookupService(
        target_repo=FakeTargetRepository(targets),
        vendor_config_repo=FakeVendorConfigRepository(configs),
        browser=FakeBrowser(html),
    )


def test_lookup_resolves_target_id_using_sorted_list_and_extracts_version_and_url():
    target_a = Target(name="Zebra", vendor="Other", vendor_alias="zebra")
    target_b = Target(name="Canon MF654Cdw", vendor="Canon", vendor_alias="canon-mf654cdw")
    config = VendorConfig(
        vendor="Canon",
        url_template="https://vendor.example/downloads/{alias}/firmware",
        attr_id="firmware",
        regex=r"Version ([^<]+).*href=\"([^\"]+)\"",
    )
    service = _service(
        [target_a, target_b],
        [config],
        '<a href="/files/fw-2.1.0.bin">Version 2.1.0</a>',
    )

    result = service.lookup(1)

    assert result.target_name == "Canon MF654Cdw"
    assert result.vendor == "Canon"
    assert result.resolved_url == "https://vendor.example/downloads/canon-mf654cdw/firmware"
    assert result.version == "2.1.0"
    assert result.download_url == "https://vendor.example/files/fw-2.1.0.bin"
    assert result.html_snippet == '<a href="/files/fw-2.1.0.bin">Version 2.1.0</a>'


def test_lookup_url_encodes_vendor_alias():
    target = Target(name="Camera", vendor="Canon", vendor_alias="model x")
    config = VendorConfig(
        vendor="Canon",
        url_template="https://vendor.example/downloads/{alias}",
        attr_id="firmware",
        regex=r"Version ([^<]+).*href=\"([^\"]+)\"",
    )
    browser = FakeBrowser('<a href="https://vendor.example/fw.bin">Version 1.0</a>')
    service = FirmwareLookupService(
        target_repo=FakeTargetRepository([target]),
        vendor_config_repo=FakeVendorConfigRepository([config]),
        browser=browser,
    )

    service.lookup(1)

    assert browser.calls == [("https://vendor.example/downloads/model%20x", "firmware")]


@pytest.mark.parametrize(
    "target_id,message",
    [
        (0, "Invalid target ID"),
        (2, "Invalid target ID"),
    ],
)
def test_lookup_rejects_invalid_target_id(target_id, message):
    service = _service([Target(name="Canon", vendor="Canon", vendor_alias="canon")], [], "")

    with pytest.raises(FirmwareLookupError, match=message):
        service.lookup(target_id)


def test_lookup_rejects_target_without_vendor():
    service = _service([Target(name="Canon", vendor_alias="canon")], [], "")

    with pytest.raises(FirmwareLookupError, match="Target 'Canon' has no vendor"):
        service.lookup(1)


def test_lookup_rejects_target_without_vendor_alias():
    service = _service([Target(name="Canon", vendor="Canon")], [], "")

    with pytest.raises(FirmwareLookupError, match="vendor_alias"):
        service.lookup(1)


def test_lookup_rejects_missing_vendor_config():
    service = _service([Target(name="Canon", vendor="Canon", vendor_alias="canon")], [], "")

    with pytest.raises(FirmwareLookupError, match="No firmware vendor config found for Canon"):
        service.lookup(1)


def test_lookup_rejects_regex_without_match():
    target = Target(name="Canon", vendor="Canon", vendor_alias="canon")
    config = VendorConfig(
        vendor="Canon",
        url_template="https://vendor.example/{alias}",
        attr_id="firmware",
        regex="Firmware ([0-9.]+) href='([^']+)'",
    )
    service = _service([target], [config], "no firmware here")

    with pytest.raises(FirmwareLookupError, match="Regex did not match"):
        service.lookup(1)


def test_lookup_rejects_non_https_download_url():
    target = Target(name="Canon", vendor="Canon", vendor_alias="canon")
    config = VendorConfig(
        vendor="Canon",
        url_template="https://vendor.example/{alias}",
        attr_id="firmware",
        regex=r"Version ([^<]+).*href=\"([^\"]+)\"",
    )
    service = _service([target], [config], '<a href="http://vendor.example/fw.bin">Version 1.0</a>')

    with pytest.raises(FirmwareLookupError, match="download URL must be relative or HTTPS"):
        service.lookup(1)


def test_validate_vendor_config_rejects_bad_config():
    with pytest.raises(FirmwareLookupError, match="HTTPS"):
        validate_vendor_config(
            VendorConfig(vendor="Canon", url_template="http://vendor.example/{alias}", attr_id="firmware", regex="(.+) (.+)")
        )

    with pytest.raises(FirmwareLookupError, match="\{alias\}"):
        validate_vendor_config(
            VendorConfig(vendor="Canon", url_template="https://vendor.example/downloads", attr_id="firmware", regex="(.+) (.+)")
        )

    with pytest.raises(FirmwareLookupError, match="at least two capture groups"):
        validate_vendor_config(
            VendorConfig(vendor="Canon", url_template="https://vendor.example/{alias}", attr_id="firmware", regex="(.+)")
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/application/test_firmware_lookup.py -q
```

Expected: FAIL because `updater.application.firmware_lookup` does not exist.

- [ ] **Step 3: Implement service**

Create `src/updater/application/firmware_lookup.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, urljoin, urlparse

from updater.domain.models import Target, VendorConfig
from updater.domain.repositories import TargetRepository, VendorConfigRepository


class FirmwareLookupError(Exception):
    pass


class BrowserAdapter(Protocol):
    def fetch_element_html(self, url: str, element_id: str) -> str: ...


@dataclass(frozen=True)
class FirmwareLookupResult:
    target_name: str
    vendor: str
    resolved_url: str
    version: str
    download_url: str
    html_snippet: str


def _sorted_targets(targets: list[Target]) -> list[Target]:
    return sorted(targets, key=lambda target: target.name.casefold())


def validate_vendor_config(config: VendorConfig) -> None:
    parsed = urlparse(config.url_template)
    if parsed.scheme != "https":
        raise FirmwareLookupError("Vendor URL template must use HTTPS")
    if "{alias}" not in config.url_template:
        raise FirmwareLookupError("Vendor URL template must contain {alias}")
    try:
        compiled = re.compile(config.regex, re.DOTALL)
    except re.error as exc:
        raise FirmwareLookupError(f"Vendor regex is invalid: {exc}") from exc
    if compiled.groups < 2:
        raise FirmwareLookupError("Vendor regex must have at least two capture groups")


def _render_url(template: str, vendor_alias: str) -> str:
    return template.replace("{alias}", quote(vendor_alias, safe=""))


def _resolve_download_url(page_url: str, captured_url: str) -> str:
    resolved = urljoin(page_url, captured_url.strip())
    parsed = urlparse(resolved)
    if parsed.scheme != "https":
        raise FirmwareLookupError("Captured download URL must be relative or HTTPS")
    return resolved


class FirmwareLookupService:
    def __init__(
        self,
        target_repo: TargetRepository,
        vendor_config_repo: VendorConfigRepository,
        browser: BrowserAdapter,
    ) -> None:
        self.target_repo = target_repo
        self.vendor_config_repo = vendor_config_repo
        self.browser = browser

    def lookup(self, target_id: int) -> FirmwareLookupResult:
        targets = _sorted_targets(self.target_repo.list_all())
        if target_id < 1 or target_id > len(targets):
            raise FirmwareLookupError(f"Invalid target ID. Use /list-targets to see available targets (1-{len(targets)}).")

        target = targets[target_id - 1]
        if not target.vendor:
            raise FirmwareLookupError(f"Target {target.name!r} has no vendor. Set vendor before firmware lookup.")
        if not target.vendor_alias:
            raise FirmwareLookupError(f"Target {target.name!r} has no vendor_alias. Set vendor_alias before firmware lookup.")

        config = self.vendor_config_repo.find_by_vendor(target.vendor)
        if config is None:
            raise FirmwareLookupError(f"No firmware vendor config found for {target.vendor}.")
        validate_vendor_config(config)

        resolved_url = _render_url(config.url_template, target.vendor_alias)
        html = self.browser.fetch_element_html(resolved_url, config.attr_id)
        match = re.search(config.regex, html, re.DOTALL)
        if match is None:
            raise FirmwareLookupError(f"Regex did not match element #{config.attr_id} at {resolved_url}.")

        version = match.group(1).strip()
        download_url = _resolve_download_url(resolved_url, match.group(2))
        return FirmwareLookupResult(
            target_name=target.name,
            vendor=target.vendor,
            resolved_url=resolved_url,
            version=version,
            download_url=download_url,
            html_snippet=html,
        )
```

- [ ] **Step 4: Run service tests**

Run:

```bash
pytest tests/application/test_firmware_lookup.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/application/firmware_lookup.py tests/application/test_firmware_lookup.py
git commit -m "feat: add firmware lookup service"
```

---

### Task 4: Add Playwright/CloakBrowser adapter boundary

**Files:**
- Create: `src/updater/infrastructure/browser/__init__.py`
- Create: `src/updater/infrastructure/browser/cloak.py`
- Modify: `pyproject.toml`
- Create: `tests/infrastructure/test_cloak_browser_adapter.py`

- [ ] **Step 1: Write failing browser adapter tests**

Create `tests/infrastructure/test_cloak_browser_adapter.py`:

```python
import pytest

from updater.infrastructure.browser.cloak import CloakBrowserAdapter, BrowserLaunchError


def test_cloak_browser_adapter_requires_dependencies(monkeypatch):
    def fake_import(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("updater.infrastructure.browser.cloak.import_module", fake_import)

    adapter = CloakBrowserAdapter()

    with pytest.raises(BrowserLaunchError, match="playwright"):
        adapter.fetch_element_html("https://vendor.example/page", "firmware")


def test_cloak_browser_adapter_rejects_missing_element(monkeypatch):
    class FakeLocator:
        def count(self):
            return 0

    class FakePage:
        def goto(self, url, wait_until, timeout):
            self.url = url

        def locator(self, selector):
            self.selector = selector
            return FakeLocator()

    class FakeContext:
        def new_page(self):
            return FakePage()

        def close(self):
            self.closed = True

    class FakeBrowser:
        def new_context(self, **kwargs):
            return FakeContext()

        def close(self):
            self.closed = True

    class FakeChromium:
        def launch(self, **kwargs):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def stop(self):
            self.stopped = True

    class FakeSyncPlaywright:
        def start(self):
            return FakePlaywright()

    def fake_import(name):
        class FakeModule:
            @staticmethod
            def sync_playwright():
                return FakeSyncPlaywright()

        return FakeModule()

    monkeypatch.setattr("updater.infrastructure.browser.cloak.import_module", fake_import)

    adapter = CloakBrowserAdapter()

    with pytest.raises(BrowserLaunchError, match="Element #firmware not found"):
        adapter.fetch_element_html("https://vendor.example/page", "firmware")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/infrastructure/test_cloak_browser_adapter.py -q
```

Expected: FAIL because the adapter module does not exist.

- [ ] **Step 3: Add Playwright dependency and adapter exports**

In `pyproject.toml`, add `playwright>=1.44.0` to `[project].dependencies`:

```toml
dependencies = [
    "beautifulsoup4>=4.12.0",
    "discord.py>=2.3.0",
    "playwright>=1.44.0",
    "pymongo>=4.6.0",
    "python-dotenv>=1.0.0",
    "requests>=2.31.0",
]
```

Create `src/updater/infrastructure/browser/__init__.py`:

```python
from updater.infrastructure.browser.cloak import BrowserLaunchError, CloakBrowserAdapter

__all__ = ["BrowserLaunchError", "CloakBrowserAdapter"]
```

- [ ] **Step 4: Implement adapter**

Create `src/updater/infrastructure/browser/cloak.py`:

```python
from __future__ import annotations

from importlib import import_module
from typing import Any


class BrowserLaunchError(Exception):
    pass


class CloakBrowserAdapter:
    def __init__(self, *, timeout_ms: int = 30_000, headless: bool = True) -> None:
        self.timeout_ms = timeout_ms
        self.headless = headless

    def fetch_element_html(self, url: str, element_id: str) -> str:
        try:
            playwright_api = import_module("playwright.sync_api")
        except ModuleNotFoundError as exc:
            raise BrowserLaunchError(
                "playwright is required for firmware lookup; install dependencies and run `playwright install chromium`."
            ) from exc

        playwright = playwright_api.sync_playwright().start()
        browser: Any | None = None
        context: Any | None = None
        try:
            browser = playwright.chromium.launch(headless=self.headless)
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
            locator = page.locator(f"#{element_id}")
            if locator.count() == 0:
                raise BrowserLaunchError(f"Element #{element_id} not found at {url}.")
            return locator.first.inner_html(timeout=self.timeout_ms)
        except BrowserLaunchError:
            raise
        except Exception as exc:
            raise BrowserLaunchError(f"Browser lookup failed for {url}: {exc}") from exc
        finally:
            if context is not None:
                context.close()
            if browser is not None:
                browser.close()
            playwright.stop()
```

This adapter uses Playwright directly while keeping the CloakBrowser integration isolated. Once the exact CloakBrowser Python API is confirmed locally, change only this file to launch through that package.

- [ ] **Step 5: Run adapter tests**

Run:

```bash
pytest tests/infrastructure/test_cloak_browser_adapter.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/updater/infrastructure/browser tests/infrastructure/test_cloak_browser_adapter.py
git commit -m "feat: add firmware browser adapter boundary"
```

---

### Task 5: Add vendor config CLI

**Files:**
- Create: `src/updater/cli/__init__.py`
- Create: `src/updater/cli/vendor_config.py`
- Modify: `pyproject.toml`
- Create: `tests/cli/test_vendor_config_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/cli/test_vendor_config_cli.py`:

```python
from updater.cli.vendor_config import main
from updater.domain.models import VendorConfig


class FakeRepo:
    def __init__(self):
        self.configs = {}
        self.deleted = []

    def upsert(self, config):
        self.configs[config.normalized_vendor] = config
        return config

    def list_all(self):
        return list(self.configs.values())

    def delete(self, vendor):
        self.deleted.append(vendor)
        return self.configs.pop(vendor.strip().lower(), None) is not None


def test_vendor_config_add_validates_and_saves(capsys):
    repo = FakeRepo()

    code = main(
        [
            "add",
            "--vendor",
            "Canon",
            "--url-template",
            "https://vendor.example/{alias}",
            "--attr-id",
            "firmware",
            "--regex",
            r"Version ([^<]+).*href=\"([^\"]+)\"",
        ],
        repo=repo,
    )

    assert code == 0
    assert repo.configs["canon"].vendor == "Canon"
    assert "Saved vendor config: Canon" in capsys.readouterr().out


def test_vendor_config_add_rejects_invalid_regex(capsys):
    repo = FakeRepo()

    code = main(
        [
            "add",
            "--vendor",
            "Canon",
            "--url-template",
            "https://vendor.example/{alias}",
            "--attr-id",
            "firmware",
            "--regex",
            "(.+)",
        ],
        repo=repo,
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "at least two capture groups" in captured.err
    assert repo.configs == {}


def test_vendor_config_list_prints_configs(capsys):
    repo = FakeRepo()
    repo.upsert(
        VendorConfig(
            vendor="Canon",
            url_template="https://vendor.example/{alias}",
            attr_id="firmware",
            regex="(.+) (.+)",
        )
    )

    code = main(["list"], repo=repo)

    assert code == 0
    assert "Canon" in capsys.readouterr().out


def test_vendor_config_remove_deletes_config(capsys):
    repo = FakeRepo()
    repo.upsert(
        VendorConfig(
            vendor="Canon",
            url_template="https://vendor.example/{alias}",
            attr_id="firmware",
            regex="(.+) (.+)",
        )
    )

    code = main(["remove", "--vendor", "Canon"], repo=repo)

    assert code == 0
    assert repo.configs == {}
    assert "Removed vendor config: Canon" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/cli/test_vendor_config_cli.py -q
```

Expected: FAIL because `updater.cli.vendor_config` does not exist.

- [ ] **Step 3: Implement CLI package and vendor config command**

Create `src/updater/cli/__init__.py`:

```python
"""Command-line entry points for updater prototypes."""
```

Create `src/updater/cli/vendor_config.py`:

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from updater.application.firmware_lookup import FirmwareLookupError, validate_vendor_config
from updater.domain.models import VendorConfig
from updater.infrastructure.mongo import MongoDatabase, MongoVendorConfigRepository
from updater.presentation.discord_bot.config import ConfigError, load_config


def _build_repo(env_path: Path):
    config = load_config(env_path)
    db = MongoDatabase(uri=config.mongodb_uri, database=config.mongodb_database)
    return MongoVendorConfigRepository(db.db)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vendor-config")
    parser.add_argument("--env", default=".env", help="Path to .env file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add")
    add.add_argument("--vendor", required=True)
    add.add_argument("--url-template", required=True)
    add.add_argument("--attr-id", required=True)
    add.add_argument("--regex", required=True)

    subparsers.add_parser("list")

    remove = subparsers.add_parser("remove")
    remove.add_argument("--vendor", required=True)
    return parser


def main(argv: list[str] | None = None, *, repo=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        repository = repo or _build_repo(Path(args.env))
        if args.command == "add":
            config = VendorConfig(
                vendor=args.vendor,
                url_template=args.url_template,
                attr_id=args.attr_id,
                regex=args.regex,
            )
            validate_vendor_config(config)
            repository.upsert(config)
            print(f"Saved vendor config: {args.vendor}")
            return 0
        if args.command == "list":
            configs = repository.list_all()
            if not configs:
                print("No vendor configs.")
                return 0
            for config in configs:
                print(f"{config.vendor}: attr_id={config.attr_id} url_template={config.url_template}")
            return 0
        if args.command == "remove":
            if repository.delete(args.vendor):
                print(f"Removed vendor config: {args.vendor}")
                return 0
            print(f"Vendor config not found: {args.vendor}", file=sys.stderr)
            return 1
    except (ConfigError, FirmwareLookupError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add console script**

In `pyproject.toml`, update `[project.scripts]`:

```toml
[project.scripts]
updater-bot = "updater.presentation.discord_bot.bot:main"
firmware-lookup = "updater.cli.firmware_lookup:main"
vendor-config = "updater.cli.vendor_config:main"
```

The `firmware-lookup` script target is added now and implemented in Task 6.

- [ ] **Step 5: Run CLI tests**

Run:

```bash
pytest tests/cli/test_vendor_config_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/updater/cli tests/cli/test_vendor_config_cli.py
git commit -m "feat: add vendor config CLI"
```

---

### Task 6: Add firmware lookup CLI

**Files:**
- Create: `src/updater/cli/firmware_lookup.py`
- Create: `tests/cli/test_firmware_lookup_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/cli/test_firmware_lookup_cli.py`:

```python
from updater.application.firmware_lookup import FirmwareLookupError, FirmwareLookupResult
from updater.cli import firmware_lookup


class FakeService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def lookup(self, target_id):
        self.calls.append(target_id)
        if self.error is not None:
            raise self.error
        return self.result


def test_firmware_lookup_cli_prints_result(capsys):
    service = FakeService(
        FirmwareLookupResult(
            target_name="Canon MF654Cdw",
            vendor="Canon",
            resolved_url="https://vendor.example/downloads/canon-mf654cdw/firmware",
            version="2.1.0",
            download_url="https://vendor.example/files/fw.bin",
            html_snippet='<a href="/files/fw.bin">Version 2.1.0</a>',
        )
    )

    code = firmware_lookup.main(["--target-id", "2"], service=service)

    output = capsys.readouterr().out
    assert code == 0
    assert service.calls == [2]
    assert "Target: Canon MF654Cdw" in output
    assert "Vendor: Canon" in output
    assert "Firmware Version: 2.1.0" in output
    assert "Download URL: https://vendor.example/files/fw.bin" in output


def test_firmware_lookup_cli_prints_errors(capsys):
    service = FakeService(error=FirmwareLookupError("No firmware vendor config found for Canon."))

    code = firmware_lookup.main(["--target-id", "1"], service=service)

    captured = capsys.readouterr()
    assert code == 2
    assert "No firmware vendor config found for Canon." in captured.err
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/cli/test_firmware_lookup_cli.py -q
```

Expected: FAIL because `updater.cli.firmware_lookup` does not exist.

- [ ] **Step 3: Implement firmware lookup CLI**

Create `src/updater/cli/firmware_lookup.py`:

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from updater.application.firmware_lookup import FirmwareLookupError, FirmwareLookupService
from updater.infrastructure.browser import BrowserLaunchError, CloakBrowserAdapter
from updater.infrastructure.mongo import MongoDatabase, MongoTargetRepository, MongoVendorConfigRepository
from updater.presentation.discord_bot.config import ConfigError, load_config


def _build_service(env_path: Path) -> FirmwareLookupService:
    config = load_config(env_path)
    db = MongoDatabase(uri=config.mongodb_uri, database=config.mongodb_database)
    return FirmwareLookupService(
        target_repo=MongoTargetRepository(db.db),
        vendor_config_repo=MongoVendorConfigRepository(db.db),
        browser=CloakBrowserAdapter(),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="firmware-lookup")
    parser.add_argument("--env", default=".env", help="Path to .env file")
    parser.add_argument("--target-id", required=True, type=int, help="Target number from /list-targets")
    return parser


def main(argv: list[str] | None = None, *, service=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        lookup_service = service or _build_service(Path(args.env))
        result = lookup_service.lookup(args.target_id)
    except (ConfigError, FirmwareLookupError, BrowserLaunchError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"Target: {result.target_name}")
    print(f"Vendor: {result.vendor}")
    print(f"Resolved URL: {result.resolved_url}")
    print(f"Firmware Version: {result.version}")
    print(f"Download URL: {result.download_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
pytest tests/cli/test_firmware_lookup_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/cli/firmware_lookup.py tests/cli/test_firmware_lookup_cli.py
git commit -m "feat: add firmware lookup CLI"
```

---

### Task 7: Update README and run full verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README target CSV section**

In `README.md`, add `vendor_alias` to the optional columns list:

```markdown
- `vendor_alias` — vendor-defined product slug/model identifier used by firmware lookup URL templates
```

Update the example CSV with aliases and version metadata to include `vendor_alias`:

```csv
name,aliases,vendor,vendor_alias,category,version,version_type
Adobe Acrobat Reader,Acrobat Reader;Adobe Reader,Adobe,acrobat-reader,document reader,2024.005.20320,software
VMware Workstation,VMware Workstation Pro;Workstation,VMware,workstation-pro,virtualization,,
```

- [ ] **Step 2: Add firmware lookup prototype docs**

In `README.md`, add this section after the slash command table:

```markdown
## Firmware lookup prototype CLI

The firmware lookup prototype is CLI-only. It resolves a target by the same numbered ID shown by `/list-targets`, uses `Target.vendor_alias` as the vendor-defined product slug, and uses a per-vendor crawler config to fetch and parse the vendor firmware page.

Add or update a vendor crawler config:

```bash
vendor-config add \
  --vendor "Canon" \
  --url-template "https://vendor.example/downloads/{alias}/firmware" \
  --attr-id "firmware" \
  --regex "Version ([^<]+).*href=\"([^\"]+)\""
```

Run a lookup:

```bash
firmware-lookup --target-id 2
```

Regex capture group 1 is the firmware version. Capture group 2 is the firmware download URL. Vendor URL templates must use HTTPS and contain `{alias}`.
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
pytest tests/domain/test_models.py tests/application/test_firmware_lookup.py tests/infrastructure/test_csv_loader.py tests/infrastructure/test_mongo_mapping.py tests/infrastructure/test_cloak_browser_adapter.py tests/cli/test_vendor_config_cli.py tests/cli/test_firmware_lookup_cli.py -q
```

Expected: PASS.

- [ ] **Step 4: Run full test suite**

Run:

```bash
pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document firmware lookup prototype"
```

---

## Self-Review Notes

- Spec coverage: target `vendor_alias`, per-vendor config, URL template validation, HTML element ID lookup, regex group 1/2 extraction, relative URL resolution, CLI usage, Mongo persistence, CSV import, and fake-browser unit tests are each covered by tasks above.
- Placeholder scan: no implementation step depends on undefined paths or future decisions. CloakBrowser’s exact package API remains intentionally isolated in `src/updater/infrastructure/browser/cloak.py` because the API could not be confirmed from the environment.
- Type consistency: the plan consistently uses `VendorConfig`, `VendorConfigRepository`, `FirmwareLookupService.lookup(target_id: int)`, `BrowserAdapter.fetch_element_html(url, element_id)`, and `vendor_alias`.
