# Target Version Checkers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add on-demand version checkers for ten Pwn2Own targets so the existing lookup command returns each target's current published version, extracted at call time from its exact vendor URL.

**Architecture:** Extend the existing firmware-lookup engine (one config schema, relaxed) rather than adding a parallel subsystem. `VendorConfig` gains per-target binding, an `http` fetch mode, an optional CSS selector, and a match-selection strategy (`first`/`last`/`max`). A new `HttpFetchAdapter` (requests + BeautifulSoup) fetches the ten server-rendered pages; the Playwright browser path is retained unchanged for legacy firmware targets. Ten target-bound configs are seeded from a built-in data module and validated against captured HTML fixtures.

**Tech Stack:** Python 3.10+, `requests`, `beautifulsoup4`, `playwright` (legacy path only), `pymongo`, `discord.py`, `pytest`/`pytest-asyncio`.

**Spec:** `docs/superpowers/specs/2026-08-17-target-version-checkers-design.md`

## Global Constraints

- All ten seed checkers use `fetch = "http"` and fetch the **exact URL** from the spec's target table (no substitution).
- Checkers report the **newest stable, publicly released** version — exclude unreleased / rc / dev / alpha entries.
- `url_template` must be HTTPS. `{alias}` is optional; when absent, `vendor_alias` is not required.
- A regex must compile and have **≥1 capture group**: group 1 = version (required), group 2 = download URL (optional).
- The HTTP fetch MUST send a browser-like `User-Agent`.
- Backward compatibility is mandatory: existing `VendorConfig` rows, the Playwright `fetch_element_html` path, and all `firmware-*` command names keep working. New model fields are optional with legacy defaults (`fetch="browser"`, `select="first"`, empty `target`/`selector`/`attr_id`).
- Seed `VendorConfig.vendor` is set to the target's name (unique) to satisfy the existing unique `normalized_vendor` index without an index migration.

---

### Task 1: Extend `VendorConfig` model and relax validation

**Files:**
- Modify: `src/updater/domain/models.py:63-75` (VendorConfig)
- Modify: `src/updater/application/firmware_lookup.py:34-49` (validation)
- Test: `tests/domain/test_models.py`, `tests/application/test_firmware_lookup.py:198-212`

**Interfaces:**
- Produces: `VendorConfig(vendor, url_template, attr_id="", regex="", target=None, fetch="browser", selector=None, select="first", id=None, created_at, updated_at)` with property `normalized_target -> str | None`; `validate_vendor_inputs(url_template, regex)` (HTTPS + ≥1 group, `{alias}` optional); `validate_vendor_config(config)` (also checks `fetch`, `select`).

- [ ] **Step 1: Write the failing test**

Append to `tests/domain/test_models.py`:

```python
def test_vendor_config_new_fields_default_to_legacy_behavior():
    from updater.domain.models import VendorConfig

    config = VendorConfig(vendor="Canon", url_template="https://x/{alias}", regex="(.+)")
    assert config.attr_id == ""
    assert config.target is None
    assert config.fetch == "browser"
    assert config.selector is None
    assert config.select == "first"
    assert config.normalized_target is None


def test_vendor_config_normalized_target():
    from updater.domain.models import VendorConfig

    config = VendorConfig(vendor="Chroma", url_template="https://x", regex="(.+)", target="  Chroma  ")
    assert config.normalized_target == "chroma"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/domain/test_models.py -k vendor_config -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'target'` (and `attr_id`/`regex` are still required).

- [ ] **Step 3: Extend the model**

In `src/updater/domain/models.py`, replace the `VendorConfig` dataclass with:

```python
@dataclass
class VendorConfig:
    vendor: str
    url_template: str
    attr_id: str = ""
    regex: str = ""
    target: str | None = None
    fetch: str = "browser"
    selector: str | None = None
    select: str = "first"
    id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def normalized_vendor(self) -> str:
        return normalize_name(self.vendor)

    @property
    def normalized_target(self) -> str | None:
        return normalize_name(self.target) if self.target else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/domain/test_models.py -k vendor_config -v`
Expected: PASS.

- [ ] **Step 5: Write the failing validation test**

Replace `test_validate_vendor_config_rejects_bad_config` in `tests/application/test_firmware_lookup.py` (lines 198-212) with:

```python
def test_validate_vendor_config_rejects_non_https():
    with pytest.raises(FirmwareLookupError, match="HTTPS"):
        validate_vendor_config(
            VendorConfig(vendor="Canon", url_template="http://vendor.example/{alias}", regex="(.+)")
        )


def test_validate_vendor_config_allows_missing_alias_placeholder():
    # {alias} is now optional; a fixed URL with one capture group is valid.
    validate_vendor_config(
        VendorConfig(vendor="Canon", url_template="https://vendor.example/releases", regex="(.+)")
    )


def test_validate_vendor_config_requires_at_least_one_group():
    with pytest.raises(FirmwareLookupError, match="at least one capture group"):
        validate_vendor_config(
            VendorConfig(vendor="Canon", url_template="https://vendor.example/x", regex="no groups")
        )


def test_validate_vendor_config_rejects_bad_fetch_and_select():
    with pytest.raises(FirmwareLookupError, match="fetch"):
        validate_vendor_config(
            VendorConfig(vendor="C", url_template="https://x", regex="(.+)", fetch="ftp")
        )
    with pytest.raises(FirmwareLookupError, match="select"):
        validate_vendor_config(
            VendorConfig(vendor="C", url_template="https://x", regex="(.+)", select="middle")
        )
```

- [ ] **Step 6: Run test to verify it fails**

Run: `python -m pytest tests/application/test_firmware_lookup.py -k validate_vendor_config -v`
Expected: FAIL — the old `{alias}`/two-group rules still fire; new `fetch`/`select` checks don't exist.

- [ ] **Step 7: Relax and extend validation**

In `src/updater/application/firmware_lookup.py`, replace `validate_vendor_inputs` and `validate_vendor_config`:

```python
def validate_vendor_inputs(url_template: str, regex: str) -> None:
    parsed = urlparse(url_template)
    if parsed.scheme != "https":
        raise FirmwareLookupError("Vendor URL template must use HTTPS")
    try:
        compiled = re.compile(regex, re.DOTALL)
    except re.error as exc:
        raise FirmwareLookupError(f"Vendor regex is invalid: {exc}") from exc
    if compiled.groups < 1:
        raise FirmwareLookupError("Vendor regex must have at least one capture group")


def validate_vendor_config(config: VendorConfig) -> None:
    validate_vendor_inputs(config.url_template, config.regex)
    if config.fetch not in ("browser", "http"):
        raise FirmwareLookupError("Vendor config fetch must be 'browser' or 'http'")
    if config.select not in ("first", "last", "max"):
        raise FirmwareLookupError("Vendor config select must be 'first', 'last', or 'max'")
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/application/test_firmware_lookup.py tests/domain/test_models.py -v`
Expected: PASS (the relaxed `{alias}` rule means the two runtime-input and lookup tests that use `{alias}` templates still pass; nothing else regresses).

- [ ] **Step 9: Commit**

```bash
git add src/updater/domain/models.py src/updater/application/firmware_lookup.py tests/domain/test_models.py tests/application/test_firmware_lookup.py
git commit -m "feat: extend VendorConfig with target/fetch/selector/select and relax validation"
```

---

### Task 2: Persist new fields and add per-target repository resolution

**Files:**
- Modify: `src/updater/infrastructure/mongo.py:86-107` (mapping), `:193-205` (indexes), `:261-285` (repo)
- Modify: `src/updater/domain/repositories.py:21-25` (protocol)
- Test: `tests/infrastructure/test_mongo_mapping.py`

**Interfaces:**
- Consumes: `VendorConfig` from Task 1.
- Produces: `vendor_config_to_document` / `vendor_config_from_document` round-trip all new fields (old documents default correctly); `MongoVendorConfigRepository.find_by_target(target: Target) -> VendorConfig | None`; `VendorConfigRepository` protocol gains `find_by_target`.

- [ ] **Step 1: Write the failing test**

Append to `tests/infrastructure/test_mongo_mapping.py`:

```python
def test_vendor_config_document_round_trip_with_new_fields():
    from updater.domain.models import VendorConfig
    from updater.infrastructure.mongo import (
        vendor_config_from_document,
        vendor_config_to_document,
    )

    config = VendorConfig(
        vendor="Chroma",
        url_template="https://github.com/chroma-core/chroma/releases",
        regex=r'releases/tag/(\d+\.\d+\.\d+)(?=["/#?])',
        target="Chroma",
        fetch="http",
        selector=None,
        select="max",
    )
    document = vendor_config_to_document(config)
    assert document["normalized_target"] == "chroma"
    assert document["fetch"] == "http"
    assert document["select"] == "max"

    restored = vendor_config_from_document({**document, "_id": "abc"})
    assert restored.target == "Chroma"
    assert restored.fetch == "http"
    assert restored.select == "max"
    assert restored.selector is None


def test_vendor_config_from_legacy_document_defaults_new_fields():
    from updater.infrastructure.mongo import vendor_config_from_document

    legacy = {
        "_id": "1",
        "vendor": "Canon",
        "url_template": "https://x/{alias}",
        "attr_id": "firmware",
        "regex": "(.+) (.+)",
        "created_at": __import__("datetime").datetime(2026, 1, 1),
        "updated_at": __import__("datetime").datetime(2026, 1, 1),
    }
    restored = vendor_config_from_document(legacy)
    assert restored.fetch == "browser"
    assert restored.select == "first"
    assert restored.target is None
    assert restored.selector is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/infrastructure/test_mongo_mapping.py -k vendor_config -v`
Expected: FAIL — `KeyError`/`AssertionError`; the mapping ignores the new fields.

- [ ] **Step 3: Update the mapping**

In `src/updater/infrastructure/mongo.py`, replace `vendor_config_to_document` and `vendor_config_from_document`:

```python
def vendor_config_to_document(config: VendorConfig) -> dict[str, Any]:
    return {
        "vendor": config.vendor,
        "normalized_vendor": config.normalized_vendor,
        "url_template": config.url_template,
        "attr_id": config.attr_id,
        "regex": config.regex,
        "target": config.target,
        "normalized_target": config.normalized_target,
        "fetch": config.fetch,
        "selector": config.selector,
        "select": config.select,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


def vendor_config_from_document(document: dict[str, Any]) -> VendorConfig:
    return VendorConfig(
        id=_document_id(document),
        vendor=document["vendor"],
        url_template=document["url_template"],
        attr_id=document.get("attr_id", ""),
        regex=document.get("regex", ""),
        target=document.get("target"),
        fetch=document.get("fetch", "browser"),
        selector=document.get("selector"),
        select=document.get("select", "first"),
        created_at=document["created_at"],
        updated_at=document["updated_at"],
    )
```

- [ ] **Step 4: Add the index and `find_by_target`**

In `ensure_indexes` (after the `vendor_configs` line at `:205`) add a non-unique lookup index:

```python
        self.db.vendor_configs.create_index("normalized_target")
```

In `MongoVendorConfigRepository`, add (after `find_by_vendor`):

```python
    def find_by_target(self, target: "Target") -> VendorConfig | None:
        normalized = normalize_name(target.name)
        document = self.collection.find_one({"normalized_target": normalized})
        return vendor_config_from_document(document) if document else None
```

(`Target` is already imported at the top of `mongo.py`.)

In `src/updater/domain/repositories.py`, add to `VendorConfigRepository` (after `find_by_vendor`):

```python
    def find_by_target(self, target: Target) -> VendorConfig | None: ...
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/infrastructure/test_mongo_mapping.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/updater/infrastructure/mongo.py src/updater/domain/repositories.py tests/infrastructure/test_mongo_mapping.py
git commit -m "feat: persist version-checker fields and add find_by_target resolution"
```

---

### Task 3: Add the HTTP fetch adapter

**Files:**
- Create: `src/updater/infrastructure/browser/http_fetch.py`
- Modify: `src/updater/infrastructure/browser/__init__.py`
- Test: `tests/infrastructure/test_http_fetch_adapter.py`

**Interfaces:**
- Produces: `HttpFetchAdapter(timeout=30, user_agent=DEFAULT_USER_AGENT, get=None).fetch_html(url: str, selector: str | None = None) -> str`; `HttpFetchError`. Exported from `updater.infrastructure.browser`.

- [ ] **Step 1: Write the failing test**

Create `tests/infrastructure/test_http_fetch_adapter.py`:

```python
import pytest

from updater.infrastructure.browser.http_fetch import HttpFetchAdapter, HttpFetchError


class FakeResponse:
    def __init__(self, text, status=200):
        self.text = text
        self._status = status

    def raise_for_status(self):
        if self._status >= 400:
            raise RuntimeError(f"HTTP {self._status}")


def _adapter(response, recorder=None):
    def fake_get(url, headers=None, timeout=None):
        if recorder is not None:
            recorder.append({"url": url, "headers": headers, "timeout": timeout})
        return response
    return HttpFetchAdapter(get=fake_get)


def test_fetch_html_returns_whole_body_when_no_selector():
    calls = []
    adapter = _adapter(FakeResponse("<html>0.147.0</html>"), calls)
    assert adapter.fetch_html("https://x") == "<html>0.147.0</html>"
    assert "User-Agent" in calls[0]["headers"]


def test_fetch_html_extracts_selector():
    adapter = _adapter(FakeResponse('<div><span id="v">1.5.9</span></div>'))
    assert "1.5.9" in adapter.fetch_html("https://x", "#v")


def test_fetch_html_raises_when_selector_missing():
    adapter = _adapter(FakeResponse("<div></div>"))
    with pytest.raises(HttpFetchError, match="not found"):
        adapter.fetch_html("https://x", "#missing")


def test_fetch_html_raises_on_http_error():
    adapter = _adapter(FakeResponse("boom", status=503))
    with pytest.raises(HttpFetchError, match="HTTP fetch failed"):
        adapter.fetch_html("https://x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/infrastructure/test_http_fetch_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: updater.infrastructure.browser.http_fetch`.

- [ ] **Step 3: Implement the adapter**

Create `src/updater/infrastructure/browser/http_fetch.py`:

```python
from __future__ import annotations

from typing import Any, Callable

import requests
from bs4 import BeautifulSoup


class HttpFetchError(Exception):
    pass


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class HttpFetchAdapter:
    def __init__(
        self,
        *,
        timeout: int = 30,
        user_agent: str = DEFAULT_USER_AGENT,
        get: Callable[..., Any] | None = None,
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent
        self._get = get or requests.get

    def fetch_html(self, url: str, selector: str | None = None) -> str:
        try:
            response = self._get(
                url, headers={"User-Agent": self.user_agent}, timeout=self.timeout
            )
            response.raise_for_status()
        except Exception as exc:
            raise HttpFetchError(f"HTTP fetch failed for {url}: {exc}") from exc

        text = response.text
        if not selector:
            return text
        soup = BeautifulSoup(text, "html.parser")
        element = soup.select_one(selector)
        if element is None:
            raise HttpFetchError(f"Selector {selector!r} not found at {url}.")
        return str(element)
```

- [ ] **Step 4: Export from the package**

Replace `src/updater/infrastructure/browser/__init__.py` with:

```python
from updater.infrastructure.browser.cloak import BrowserLaunchError, CloakBrowserAdapter
from updater.infrastructure.browser.http_fetch import HttpFetchAdapter, HttpFetchError

__all__ = [
    "BrowserLaunchError",
    "CloakBrowserAdapter",
    "HttpFetchAdapter",
    "HttpFetchError",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/infrastructure/test_http_fetch_adapter.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/updater/infrastructure/browser/http_fetch.py src/updater/infrastructure/browser/__init__.py tests/infrastructure/test_http_fetch_adapter.py
git commit -m "feat: add HttpFetchAdapter for server-rendered version pages"
```

---

### Task 4: Wire the lookup service for HTTP fetch, per-target configs, and match selection

**Files:**
- Modify: `src/updater/application/firmware_lookup.py` (result, service, extraction)
- Test: `tests/application/test_firmware_lookup.py`

**Interfaces:**
- Consumes: `VendorConfig` (Task 1), `find_by_target` (Task 2), `HttpFetchAdapter.fetch_html` (Task 3).
- Produces: `FirmwareLookupResult.download_url: str | None`; `FirmwareLookupService(target_repo, vendor_config_repo, browser, http=None)`; module helpers `_select_match(regex, html, select)` and `_version_key(value)`.

- [ ] **Step 1: Write the failing tests**

In `tests/application/test_firmware_lookup.py`, update `FakeVendorConfigRepository` to support target binding and add a fake HTTP adapter and new tests. Replace the `FakeVendorConfigRepository` class with:

```python
class FakeVendorConfigRepository:
    def __init__(self, configs):
        self.configs = {config.normalized_vendor: config for config in configs}

    def find_by_vendor(self, vendor):
        from updater.domain.models import normalize_name

        return self.configs.get(normalize_name(vendor))

    def find_by_target(self, target):
        from updater.domain.models import normalize_name

        norm = normalize_name(target.name)
        return next(
            (c for c in self.configs.values() if c.normalized_target == norm), None
        )
```

Add after `FakeBrowser`:

```python
class FakeHttp:
    def __init__(self, html):
        self.html = html
        self.calls = []

    def fetch_html(self, url, selector=None):
        self.calls.append((url, selector))
        return self.html
```

Append these tests:

```python
def _http_service(targets, configs, html):
    return FirmwareLookupService(
        target_repo=FakeTargetRepository(targets),
        vendor_config_repo=FakeVendorConfigRepository(configs),
        browser=FakeBrowser(""),
        http=FakeHttp(html),
    )


def test_lookup_uses_target_bound_http_config_version_only():
    target = Target(name="Chroma", vendor="Chroma")
    config = VendorConfig(
        vendor="Chroma",
        target="Chroma",
        url_template="https://github.com/chroma-core/chroma/releases",
        regex=r'releases/tag/(\d+\.\d+\.\d+)(?=["/#?])',
        fetch="http",
        select="first",
    )
    service = _http_service(
        [target], [config],
        '<a href="/chroma-core/chroma/releases/tag/cli-1.4.4">x</a>'
        '<a href="/chroma-core/chroma/releases/tag/1.5.9">x</a>',
    )
    result = service.lookup(1)
    assert result.version == "1.5.9"
    assert result.download_url is None
    assert result.resolved_url == "https://github.com/chroma-core/chroma/releases"


def test_lookup_select_max_picks_highest_version():
    target = Target(name="Oracle Autonomous AI Database", vendor="Oracle")
    config = VendorConfig(
        vendor="Oracle Autonomous AI Database",
        target="Oracle Autonomous AI Database",
        url_template="https://docs.oracle.com/x.html",
        regex=r"(?:Release Update\s+|release-update-)(\d+(?:\.\d+){1,2})",
        fetch="http",
        select="max",
    )
    service = _http_service(
        [target], [config],
        'Release Update 23.26.2 <a href="july-2026-release-update-23.26.3.html">x</a>',
    )
    assert service.lookup(1).version == "23.26.3"


def test_lookup_select_last_picks_last_match():
    target = Target(name="T", vendor="V")
    config = VendorConfig(
        vendor="T", target="T", url_template="https://x", regex=r"v(\d+)",
        fetch="http", select="last",
    )
    service = _http_service([target], [config], "v1 v2 v9 v4")
    assert service.lookup(1).version == "4"


def test_lookup_http_config_without_alias_needs_no_vendor_alias():
    target = Target(name="LiteLLM")  # no vendor, no vendor_alias
    config = VendorConfig(
        vendor="LiteLLM", target="LiteLLM",
        url_template="https://docs.litellm.ai/release_notes/",
        regex=r"(v\d+\.\d+\.\d+)", fetch="http",
    )
    service = _http_service([target], [config], "v1.97.0")
    assert service.lookup(1).version == "v1.97.0"


def test_lookup_http_config_errors_when_no_http_adapter():
    target = Target(name="Chroma")
    config = VendorConfig(
        vendor="Chroma", target="Chroma", url_template="https://x",
        regex=r"(\d+)", fetch="http",
    )
    service = FirmwareLookupService(
        target_repo=FakeTargetRepository([target]),
        vendor_config_repo=FakeVendorConfigRepository([config]),
        browser=FakeBrowser(""),
    )
    with pytest.raises(FirmwareLookupError, match="HTTP fetch adapter"):
        service.lookup(1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/application/test_firmware_lookup.py -k "http or select_max or select_last" -v`
Expected: FAIL — `TypeError` (`http` kwarg unknown) / `AttributeError` (`find_by_target`) / wrong values.

- [ ] **Step 3: Update the result and service**

In `src/updater/application/firmware_lookup.py`:

Change the result's download field:

```python
@dataclass(frozen=True)
class FirmwareLookupResult:
    target_name: str
    vendor: str
    resolved_url: str
    version: str
    download_url: str | None
    html_snippet: str
```

Add module helpers (near `_render_url`):

```python
def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value))


def _select_match(regex: str, html: str, select: str):
    matches = list(re.finditer(regex, html, re.DOTALL))
    if not matches:
        return None
    if select == "last":
        return matches[-1]
    if select == "max":
        return max(matches, key=lambda m: _version_key(m.group(1)))
    return matches[0]
```

Replace the `FirmwareLookupService` class body:

```python
class FirmwareLookupService:
    def __init__(
        self,
        target_repo: TargetRepository,
        vendor_config_repo: VendorConfigRepository,
        browser: BrowserAdapter,
        http: "BrowserAdapter | None" = None,
    ) -> None:
        self.target_repo = target_repo
        self.vendor_config_repo = vendor_config_repo
        self.browser = browser
        self.http = http

    def lookup(self, target_id: int) -> FirmwareLookupResult:
        target = self._target_by_id(target_id)

        bound = self.vendor_config_repo.find_by_target(target)
        if bound is not None:
            validate_vendor_config(bound)
            if "{alias}" in bound.url_template and not target.vendor_alias:
                raise FirmwareLookupError(
                    f"Target {target.name!r} has no vendor_alias. Set vendor_alias before version lookup."
                )
            return self._lookup_target(target=target, config=bound)

        if not target.vendor:
            raise FirmwareLookupError(
                f"Target {target.name!r} has no vendor. Set vendor before firmware lookup."
            )
        if not target.vendor_alias:
            raise FirmwareLookupError(
                f"Target {target.name!r} has no vendor_alias. Set vendor_alias before firmware lookup."
            )
        config = self.vendor_config_repo.find_by_vendor(target.vendor)
        if config is None:
            raise FirmwareLookupError(f"No firmware vendor config found for {target.vendor}.")
        validate_vendor_config(config)
        return self._lookup_target(target=target, config=config)

    def lookup_with_inputs(
        self, *, target_id: int, url_template: str, attr_id: str, regex: str
    ) -> FirmwareLookupResult:
        target = self._target_by_id(target_id)
        if "{alias}" in url_template and not target.vendor_alias:
            raise FirmwareLookupError(
                f"Target {target.name!r} has no vendor_alias. Set vendor_alias before version lookup."
            )
        validate_vendor_inputs(url_template, regex)
        config = VendorConfig(
            vendor=target.vendor or target.name,
            url_template=url_template,
            attr_id=attr_id,
            regex=regex,
            fetch="browser",
            select="first",
        )
        return self._lookup_target(target=target, config=config)

    def _target_by_id(self, target_id: int) -> Target:
        targets = _sorted_targets(self.target_repo.list_all())
        if target_id < 1 or target_id > len(targets):
            raise FirmwareLookupError(
                f"Invalid target ID. Use /list-targets to see available targets (1-{len(targets)})."
            )
        return targets[target_id - 1]

    def _lookup_target(self, *, target: Target, config: VendorConfig) -> FirmwareLookupResult:
        resolved_url = _render_url(config.url_template, target.vendor_alias or "")
        if config.fetch == "http":
            if self.http is None:
                raise FirmwareLookupError("HTTP fetch adapter is not configured for this lookup.")
            html = self.http.fetch_html(resolved_url, config.selector)
        else:
            html = self.browser.fetch_element_html(resolved_url, config.attr_id)

        match = _select_match(config.regex, html, config.select)
        if match is None:
            location = config.selector or (f"#{config.attr_id}" if config.attr_id else "page")
            raise FirmwareLookupError(f"Regex did not match {location} at {resolved_url}.")

        version = match.group(1).strip()
        download_url: str | None = None
        if match.re.groups >= 2 and match.group(2):
            download_url = _resolve_download_url(resolved_url, match.group(2))

        return FirmwareLookupResult(
            target_name=target.name,
            vendor=target.vendor or config.vendor or "",
            resolved_url=resolved_url,
            version=version,
            download_url=download_url,
            html_snippet=html,
        )
```

Add `VendorConfig` to the model import at the top if not present:

```python
from updater.domain.models import Target, VendorConfig
```

- [ ] **Step 4: Run the full firmware_lookup test file**

Run: `python -m pytest tests/application/test_firmware_lookup.py -v`
Expected: PASS — new HTTP/select tests pass and all legacy tests (sorted-id, url-encode, slashes, runtime-inputs, invalid-id, no-vendor, no-vendor-alias, missing-config, no-match, non-https-download) still pass.

- [ ] **Step 5: Commit**

```bash
git add src/updater/application/firmware_lookup.py tests/application/test_firmware_lookup.py
git commit -m "feat: support http fetch, per-target configs, and match selection in lookup"
```

---

### Task 5: Extend the CLI and register version-* aliases

**Files:**
- Modify: `src/updater/cli/vendor_config.py`
- Modify: `src/updater/cli/firmware_lookup.py`
- Modify: `pyproject.toml:25-28`
- Test: `tests/cli/test_vendor_config_cli.py`, `tests/cli/test_firmware_lookup_cli.py`

**Interfaces:**
- Consumes: `VendorConfig` (Task 1), `HttpFetchAdapter` (Task 3), service `http` param (Task 4).
- Produces: `vendor-config add` flags `--target/--fetch/--selector/--select` (and optional `--attr-id`); `firmware-lookup` prints Download only when present; console scripts `version-config`, `version-lookup`.

- [ ] **Step 1: Write the failing CLI tests**

In `tests/cli/test_vendor_config_cli.py`, replace `test_vendor_config_add_rejects_invalid_regex` (the `(.+)` case is now valid) with a genuinely invalid regex, and add a target-bound case:

```python
def test_vendor_config_add_rejects_invalid_regex(capsys):
    repo = FakeRepo()
    code = main(
        ["add", "--vendor", "Canon", "--url-template", "https://vendor.example/{alias}",
         "--attr-id", "firmware", "--regex", "(unbalanced"],
        repo=repo,
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "Vendor regex is invalid" in captured.err
    assert repo.configs == {}


def test_vendor_config_add_target_bound_http(capsys):
    repo = FakeRepo()
    code = main(
        ["add", "--vendor", "Chroma", "--target", "Chroma",
         "--url-template", "https://github.com/chroma-core/chroma/releases",
         "--fetch", "http", "--select", "first",
         "--regex", r'releases/tag/(\d+\.\d+\.\d+)(?=["/#?])'],
        repo=repo,
    )
    assert code == 0
    saved = repo.configs["chroma"]
    assert saved.target == "Chroma"
    assert saved.fetch == "http"
    assert saved.attr_id == ""
    assert "Saved vendor config: Chroma" in capsys.readouterr().out
```

In `tests/cli/test_firmware_lookup_cli.py`, add:

```python
def test_firmware_lookup_cli_omits_download_when_absent(capsys):
    service = FakeService(
        FirmwareLookupResult(
            target_name="Chroma", vendor="Chroma",
            resolved_url="https://github.com/chroma-core/chroma/releases",
            version="1.5.9", download_url=None, html_snippet="",
        )
    )
    code = firmware_lookup.main(["--target-id", "1"], service=service)
    output = capsys.readouterr().out
    assert code == 0
    assert "Firmware Version: 1.5.9" in output
    assert "Download URL" not in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/cli/test_vendor_config_cli.py tests/cli/test_firmware_lookup_cli.py -v`
Expected: FAIL — unknown `--target/--fetch` args; Download line always printed.

- [ ] **Step 3: Extend `vendor-config`**

In `src/updater/cli/vendor_config.py`, update the `add` subparser and construction. Replace the `add` block in `build_parser`:

```python
    add = subparsers.add_parser("add")
    add.add_argument("--vendor", required=True)
    add.add_argument("--url-template", required=True)
    add.add_argument("--attr-id", default="")
    add.add_argument("--regex", required=True)
    add.add_argument("--target")
    add.add_argument("--fetch", default="browser", choices=["browser", "http"])
    add.add_argument("--selector")
    add.add_argument("--select", default="first", choices=["first", "last", "max"])
```

Replace the `if args.command == "add":` block in `main`:

```python
        if args.command == "add":
            config = VendorConfig(
                vendor=args.vendor,
                url_template=args.url_template,
                attr_id=args.attr_id,
                regex=args.regex,
                target=args.target,
                fetch=args.fetch,
                selector=args.selector,
                select=args.select,
            )
            validate_vendor_config(config)
            repository.upsert(config)
            print(f"Saved vendor config: {args.vendor}")
            return 0
```

- [ ] **Step 4: Extend `firmware-lookup`**

In `src/updater/cli/firmware_lookup.py`, add the HTTP adapter to the built service and make the Download line conditional. Update `_build_service`:

```python
def _build_service(env_path: Path) -> FirmwareLookupService:
    config = load_config(env_path)
    db = MongoDatabase(uri=config.mongodb_uri, database=config.mongodb_database)
    return FirmwareLookupService(
        target_repo=MongoTargetRepository(db.db),
        vendor_config_repo=MongoVendorConfigRepository(db.db),
        browser=CloakBrowserAdapter(),
        http=HttpFetchAdapter(),
    )
```

Update the import at the top:

```python
from updater.infrastructure.browser import BrowserLaunchError, CloakBrowserAdapter, HttpFetchAdapter, HttpFetchError
```

Add `HttpFetchError` to the `except` tuple in `main`:

```python
    except (ConfigError, FirmwareLookupError, BrowserLaunchError, HttpFetchError, RuntimeError) as exc:
```

Replace the print block at the end of `main`:

```python
    print(f"Target: {result.target_name}")
    print(f"Vendor: {result.vendor}")
    print(f"Resolved URL: {result.resolved_url}")
    print(f"Firmware Version: {result.version}")
    if result.download_url:
        print(f"Download URL: {result.download_url}")
    return 0
```

- [ ] **Step 5: Register alias console scripts**

In `pyproject.toml`, replace the `[project.scripts]` block:

```toml
[project.scripts]
updater-bot = "updater.presentation.discord_bot.bot:main"
firmware-lookup = "updater.cli.firmware_lookup:main"
vendor-config = "updater.cli.vendor_config:main"
version-lookup = "updater.cli.firmware_lookup:main"
version-config = "updater.cli.vendor_config:main"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/cli/ -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/updater/cli/vendor_config.py src/updater/cli/firmware_lookup.py pyproject.toml tests/cli/
git commit -m "feat: extend CLI with version-checker flags and version-* aliases"
```

---

### Task 6: Extend the CSV importer for version-checker columns

**Files:**
- Modify: `src/updater/presentation/discord_bot/commands.py:481-515` (`handle_import_vendor_firmware`)
- Create: `samples/version_checks.csv`
- Test: `tests/presentation/discord_bot/test_commands.py`

**Interfaces:**
- Consumes: `VendorConfig` (Task 1), `validate_vendor_config` (Task 1).
- Produces: `handle_import_vendor_firmware` accepts optional `target`, `fetch`, `selector`, `select` columns and optional `attr_id`.

- [ ] **Step 1: Write the failing test**

Append to `tests/presentation/discord_bot/test_commands.py`:

```python
async def test_import_vendor_firmware_supports_version_checker_columns():
    csv_data = (
        "target,vendor,url_template,fetch,selector,select,regex\n"
        "Chroma,Chroma,https://github.com/chroma-core/chroma/releases,http,,first,"
        'releases/tag/(\\d+\\.\\d+\\.\\d+)\n'
    ).encode()
    services = _services()
    result = await handle_import_vendor_firmware(services, csv_bytes=csv_data)
    assert "1" in result.text
    saved = services.vendor_config_repo.find_by_vendor("Chroma")
    assert saved is not None
    assert saved.target == "Chroma"
    assert saved.fetch == "http"
    assert saved.attr_id == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/presentation/discord_bot/test_commands.py -k version_checker_columns -v`
Expected: FAIL — the importer ignores the new columns / requires `attr_id`.

- [ ] **Step 3: Update the importer**

In `src/updater/presentation/discord_bot/commands.py`, replace the body of `handle_import_vendor_firmware` (the per-row loop) with:

```python
    text = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    saved = 0
    errors: list[str] = []
    for row in reader:
        vendor = (row.get("vendor") or "").strip()
        url_template = (row.get("url_template") or "").strip()
        regex = (row.get("regex") or "").strip()
        attr_id = (row.get("attr_id") or "").strip()
        target = (row.get("target") or "").strip() or None
        fetch = (row.get("fetch") or "browser").strip() or "browser"
        selector = (row.get("selector") or "").strip() or None
        select = (row.get("select") or "first").strip() or "first"
        if not all([vendor, url_template, regex]):
            errors.append(f"Row skipped (missing fields): {vendor or '<empty>'}")
            continue
        config = VendorConfig(
            vendor=vendor,
            url_template=url_template,
            attr_id=attr_id,
            regex=regex,
            target=target,
            fetch=fetch,
            selector=selector,
            select=select,
        )
        try:
            validate_vendor_config(config)
        except FirmwareLookupError as exc:
            errors.append(f"{vendor}: {exc}")
            continue
        services.vendor_config_repo.upsert(config)
        saved += 1
    lines = [f"Imported {saved} vendor firmware config(s)."]
    if errors:
        lines.append(f"Errors ({len(errors)}):")
        lines.extend(f"  - {e}" for e in errors)
    return CommandResult(text="\n".join(lines))
```

Add `validate_vendor_config` to the firmware_lookup import at the top of `commands.py`:

```python
from updater.application.firmware_lookup import (
    BrowserAdapter,
    FirmwareLookupError,
    FirmwareLookupService,
    validate_vendor_config,
    validate_vendor_inputs,
)
```

- [ ] **Step 4: Create the sample CSV**

Create `samples/version_checks.csv` (regex fields with embedded `"` are CSV-quoted with doubled quotes):

```csv
target,vendor,url_template,fetch,selector,select,regex
Philips Hue Bridge Pro,Philips Hue Bridge Pro,https://www.philips-hue.com/en-us/support/release-notes/bridge-pro,http,,first,Software version\s+(\d{10})
OpenAI Codex,OpenAI Codex,https://learn.chatgpt.com/docs/changelog?type=codex-cli,http,,first,@openai/codex@(\d+\.\d+\.\d+)
Oracle Autonomous AI Database,Oracle Autonomous AI Database,https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/autonomous-ai-database-updates.html,http,,max,(?:Release Update\s+|release-update-)(\d+(?:\.\d+){1,2})
```

(The complete, quote-heavy set of all ten is seeded programmatically in Task 7; this CSV demonstrates the importer's new columns.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/presentation/discord_bot/test_commands.py -k "vendor_firmware" -v`
Expected: PASS (existing import tests still pass — `attr_id` is now optional but the old rows still import).

- [ ] **Step 6: Commit**

```bash
git add src/updater/presentation/discord_bot/commands.py samples/version_checks.csv tests/presentation/discord_bot/test_commands.py
git commit -m "feat: import version-checker columns from CSV"
```

---

### Task 7: Seed the ten checkers and validate each against a fixture

**Files:**
- Create: `src/updater/infrastructure/seed/__init__.py`
- Create: `src/updater/infrastructure/seed/version_checks.py`
- Modify: `src/updater/cli/vendor_config.py` (add `seed` subcommand)
- Create: `tests/fixtures/version/*.html` (ten fixtures)
- Create: `tests/infrastructure/test_version_check_seed.py`

**Interfaces:**
- Consumes: `VendorConfig`, `Target`, `_select_match` (Task 4).
- Produces: `updater.infrastructure.seed.version_checks.targets() -> list[Target]`, `version_checks() -> list[VendorConfig]`, `seed(target_repo, vendor_config_repo) -> dict[str, int]`; `vendor-config seed` command.

- [ ] **Step 1: Write the seed data module**

Create `src/updater/infrastructure/seed/__init__.py` (empty) and `src/updater/infrastructure/seed/version_checks.py`:

```python
from __future__ import annotations

from updater.domain.models import Target, VendorConfig

# (name, category, url, select, regex) — every checker uses http fetch and no selector.
_CHECKS = [
    ("Philips Hue Bridge Pro", "Smart Home",
     "https://www.philips-hue.com/en-us/support/release-notes/bridge-pro",
     "first", r"Software version\s+(\d{10})"),
    ("Samsung Galaxy S26", "Mobile Phone",
     "https://security.samsungmobile.com/securityUpdate.smsb",
     "first",
     r"(?i)SMR[ -]((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-20\d{2}\s+Release\s+\d+)"),
    ("Home Assistant Green", "Smart Home",
     "https://github.com/home-assistant/operating-system/releases",
     "first", r'releases/tag/(\d+\.\d+(?:\.\d+)?)"'),
    ("OpenAI Codex", "Coding Agent",
     "https://learn.chatgpt.com/docs/changelog?type=codex-cli",
     "first", r"@openai/codex@(\d+\.\d+\.\d+)"),
    ("Anthropic Claude Code", "Coding Agent",
     "https://code.claude.com/docs/en/changelog",
     "first", r'data-component-part="update-label"[^>]*>\s*(\d+\.\d+\.\d+)'),
    ("Postgres pgvector", "AI infrastructure",
     "https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md",
     "first", r"##\s+(\d+\.\d+\.\d+)\s+\(\d{4}-\d{2}-\d{2}\)"),
    ("Oracle Autonomous AI Database", "AI infrastructure",
     "https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/autonomous-ai-database-updates.html",
     "max", r"(?:Release Update\s+|release-update-)(\d+(?:\.\d+){1,2})"),
    ("LiteLLM", "AI infrastructure",
     "https://docs.litellm.ai/release_notes/",
     "first", r'id="?latest-release"?[\s\S]*?/release_notes/(v\d+\.\d+\.\d+)/'),
    ("NVIDIA Dynamo", "AI infrastructure",
     "https://docs.nvidia.com/dynamo/reference/releases",
     "first", r"Latest\s*\((v\d+\.\d+\.\d+)\)"),
    ("Chroma", "AI infrastructure",
     "https://github.com/chroma-core/chroma/releases",
     "first", r'releases/tag/(\d+\.\d+\.\d+)(?=["/#?])'),
]


def targets() -> list[Target]:
    return [Target(name=name, category=category) for name, category, *_ in _CHECKS]


def version_checks() -> list[VendorConfig]:
    return [
        VendorConfig(
            vendor=name,
            target=name,
            url_template=url,
            fetch="http",
            selector=None,
            select=select,
            regex=regex,
        )
        for name, _category, url, select, regex in _CHECKS
    ]


def seed(target_repo, vendor_config_repo) -> dict[str, int]:
    for target in targets():
        target_repo.upsert(target)
    for config in version_checks():
        vendor_config_repo.upsert(config)
    return {"targets": len(_CHECKS), "configs": len(_CHECKS)}
```

- [ ] **Step 2: Write the ten fixtures**

Create these files under `tests/fixtures/version/`. Each contains realistic markup **with a decoy** so the test proves the regex+select selects the right entry.

`philips.html`:
```html
<p><i>Bridge Pro Software version 2071401010</i> <b>July 13, 2026</b></p>
<p><i>Bridge Pro Software version 2071401000</i> <b>June 1, 2026</b></p>
```
`samsung.html`:
```html
<div class="acc_title" id="August"><a>SMR-AUG-2026</a></div>
<div class="acc_sub">SMR Aug-2026 Release 1</div>
<div class="acc_sub">SMR Jul-2026 Release 1</div>
```
`home_assistant.html`:
```html
<a href="/home-assistant/operating-system/releases/tag/18.2.rc1">rc</a>
<a href="/home-assistant/operating-system/releases/tag/18.2">18.2</a>
```
`codex.html`:
```html
<h3>ChatGPT for iOS <span>7.9.9</span></h3>
<pre>npm install -g @openai/codex@0.147.0</pre>
<pre>npm install -g @openai/codex@0.146.0</pre>
```
`claude_code.html`:
```html
<nav><a href="/docs">SDK 7.2.0</a></nav>
<div data-component-part="update-label">2.1.233</div>
<div data-component-part="update-label">2.1.231</div>
```
`pgvector.html`:
```html
## 0.8.7 (unreleased)
## 0.8.6 (2026-07-29)
## 0.8.5 (2026-07-08)
```
`oracle.html`:
```html
<link rel="prev" href="july-2026-release-update-23.26.3.html">
<ul class="ullinks">
<li>April 2026 — Release Update 23.26.2.</li>
<li>January 2026 — Release Update 23.26.1.</li>
</ul>
```
`litellm.html`:
```html
<meta name="generator" content="Docusaurus v3.8.1">
<nav class="menu"><a href="/release_notes/v1.98.0rc1/v1-98-0rc1">v1.98.0rc1</a></nav>
<h2 id="latest-release">Latest Release</h2>
<h3><a href="/release_notes/v1.97.0/v1-97-0">v1.97.0</a></h3>
```
`dynamo.html`:
```html
<table class="fern-table"><tr><td>v1.3.0</td></tr></table>
<div class="version-dropdown-trigger">Latest (v1.4.0)</div>
```
`chroma.html`:
```html
<a href="/chroma-core/chroma/releases/tag/latest">latest</a>
<a href="/chroma-core/chroma/releases/tag/cli-1.4.4">cli</a>
<a href="/chroma-core/chroma/releases/tag/1.5.10.dev247">dev</a>
<a href="/chroma-core/chroma/releases/tag/1.5.9">1.5.9</a>
```

- [ ] **Step 3: Write the failing seed/fixture test**

Create `tests/infrastructure/test_version_check_seed.py`:

```python
from pathlib import Path

import pytest

from updater.application.firmware_lookup import _select_match
from updater.infrastructure.seed.version_checks import seed, targets, version_checks

FIXTURES = Path(__file__).parent.parent / "fixtures" / "version"

EXPECTED = {
    "Philips Hue Bridge Pro": ("philips.html", "2071401010"),
    "Samsung Galaxy S26": ("samsung.html", "Aug-2026 Release 1"),
    "Home Assistant Green": ("home_assistant.html", "18.2"),
    "OpenAI Codex": ("codex.html", "0.147.0"),
    "Anthropic Claude Code": ("claude_code.html", "2.1.233"),
    "Postgres pgvector": ("pgvector.html", "0.8.6"),
    "Oracle Autonomous AI Database": ("oracle.html", "23.26.3"),
    "LiteLLM": ("litellm.html", "v1.97.0"),
    "NVIDIA Dynamo": ("dynamo.html", "v1.4.0"),
    "Chroma": ("chroma.html", "1.5.9"),
}


@pytest.mark.parametrize("config", version_checks(), ids=lambda c: c.target)
def test_seed_regex_extracts_expected_version_from_fixture(config):
    fixture_name, expected = EXPECTED[config.target]
    html = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    match = _select_match(config.regex, html, config.select)
    assert match is not None, f"no match for {config.target}"
    assert match.group(1).strip() == expected


def test_seed_covers_all_ten_targets():
    assert len(version_checks()) == 10
    assert {t.name for t in targets()} == set(EXPECTED)


class _Repo:
    def __init__(self):
        self.items = []

    def upsert(self, item):
        self.items.append(item)
        return item


def test_seed_upserts_targets_and_configs():
    target_repo, config_repo = _Repo(), _Repo()
    counts = seed(target_repo, config_repo)
    assert counts == {"targets": 10, "configs": 10}
    assert len(target_repo.items) == 10
    assert len(config_repo.items) == 10
```

- [ ] **Step 4: Run test to verify it fails, then passes**

Run: `python -m pytest tests/infrastructure/test_version_check_seed.py -v`
Expected: initially FAIL if any fixture/regex mismatches. Fix the offending regex in `version_checks.py` or the fixture until all ten pass. (The regexes above were validated against these fixtures during design; a failure means a typo was introduced.)

- [ ] **Step 5: Add the `seed` CLI subcommand**

In `src/updater/cli/vendor_config.py`, register the subcommand in `build_parser` (after the `remove` subparser):

```python
    subparsers.add_parser("seed")
```

Add a branch in `main` (before the final `return 2`). Because seeding also upserts targets, build both repos when needed:

```python
        if args.command == "seed":
            from updater.infrastructure.mongo import MongoDatabase, MongoTargetRepository
            from updater.infrastructure.seed.version_checks import seed as seed_version_checks

            config = load_config(Path(args.env))
            db = MongoDatabase(uri=config.mongodb_uri, database=config.mongodb_database)
            counts = seed_version_checks(
                MongoTargetRepository(db.db), MongoVendorConfigRepository(db.db)
            )
            print(f"Seeded {counts['targets']} targets and {counts['configs']} version checks.")
            return 0
```

- [ ] **Step 6: Run the full test suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/updater/infrastructure/seed/ src/updater/cli/vendor_config.py tests/fixtures/version/ tests/infrastructure/test_version_check_seed.py
git commit -m "feat: seed ten target version checkers with fixture-validated regexes"
```

---

### Task 8: Extend the Discord command surface and aliases

**Files:**
- Modify: `src/updater/presentation/discord_bot/commands.py` (`Services`, `handle_set_vendor_firmware`, `handle_lookup_firmware`)
- Modify: `src/updater/presentation/discord_bot/bot.py` (`_build_services`, command registration)
- Test: `tests/presentation/discord_bot/test_commands.py`

**Interfaces:**
- Consumes: `HttpFetchAdapter` (Task 3), extended service (Task 4).
- Produces: `Services.http`; `handle_set_vendor_firmware(..., target=None, fetch="browser", selector=None, select="first")`; `handle_lookup_firmware` prints Download only when present; `/set-version-check` and `/check-version` slash commands.

- [ ] **Step 1: Write the failing tests**

In `tests/presentation/discord_bot/test_commands.py`, update the `_services` helper (line 153) to add an `http` fake, add `find_by_target` to `FakeVendorConfigRepo` (class at line 117), and replace `test_set_vendor_firmware_rejects_missing_alias_placeholder` (the `{alias}` requirement is dropped). Then add new tests.

Update `_services`:

```python
def _services(target_repo=None, vuln_repo=None, link_repo=None, version_repo=None, sources=None, vendor_config_repo=None, browser=None, http=None):
    return Services(
        target_repo=target_repo or FakeTargetRepo(),
        version_repo=version_repo or FakeVersionRepo(),
        vulnerability_repo=vuln_repo or FakeVulnRepo(),
        target_vulnerability_repo=link_repo or FakeLinkRepo(),
        sources=sources or [],
        vendor_config_repo=vendor_config_repo or FakeVendorConfigRepo(),
        browser=browser or FakeBrowserAdapter(),
        http=http or FakeHttpAdapter(),
    )
```

Add near `FakeBrowserAdapter` (line 143):

```python
class FakeHttpAdapter:
    def __init__(self, html="v1.0.0"):
        self.html = html
        self.calls = []

    def fetch_html(self, url, selector=None):
        self.calls.append((url, selector))
        return self.html
```

Add `find_by_target` to `FakeVendorConfigRepo`:

```python
    def find_by_target(self, target):
        from updater.domain.models import normalize_name
        norm = normalize_name(target.name)
        return next((c for c in self.configs.values() if c.normalized_target == norm), None)
```

Replace `test_set_vendor_firmware_rejects_missing_alias_placeholder` with:

```python
async def test_set_vendor_firmware_allows_fixed_url_and_target_binding():
    services = _services()
    result = await handle_set_vendor_firmware(
        services,
        vendor="Chroma",
        url_template="https://github.com/chroma-core/chroma/releases",
        attr_id="",
        regex=r"releases/tag/(\d+\.\d+\.\d+)",
        target="Chroma",
        fetch="http",
    )
    assert "Chroma" in result.text
    saved = services.vendor_config_repo.find_by_vendor("Chroma")
    assert saved.target == "Chroma"
    assert saved.fetch == "http"
```

Add:

```python
async def test_check_version_uses_target_bound_http_config():
    from updater.domain.models import Target, VendorConfig
    target = Target(id="t1", name="Chroma")
    config = VendorConfig(
        vendor="Chroma", target="Chroma",
        url_template="https://github.com/chroma-core/chroma/releases",
        regex=r'releases/tag/(\d+\.\d+\.\d+)(?=["/#?])', fetch="http",
    )
    http = FakeHttpAdapter(html='<a href="/chroma-core/chroma/releases/tag/1.5.9">x</a>')
    services = _services(
        target_repo=FakeTargetRepo([target]),
        vendor_config_repo=FakeVendorConfigRepo([config]),
        http=http,
    )
    result = await handle_lookup_firmware(services, target_id=1)
    assert "1.5.9" in result.text
    assert "Download" not in result.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/presentation/discord_bot/test_commands.py -k "target_binding or check_version" -v`
Expected: FAIL — `Services` has no `http`; `handle_set_vendor_firmware` rejects extra kwargs; download always printed.

- [ ] **Step 3: Extend `Services` and handlers**

In `src/updater/presentation/discord_bot/commands.py`, add the `http` field to `Services` (after `browser`):

```python
    browser: BrowserAdapter
    http: BrowserAdapter | None = None
```

Replace `handle_set_vendor_firmware`:

```python
async def handle_set_vendor_firmware(
    services: Services,
    *,
    vendor: str,
    url_template: str,
    attr_id: str = "",
    regex: str,
    target: str | None = None,
    fetch: str = "browser",
    selector: str | None = None,
    select: str = "first",
) -> CommandResult:
    config = VendorConfig(
        vendor=vendor,
        url_template=url_template,
        attr_id=attr_id,
        regex=regex,
        target=target,
        fetch=fetch,
        selector=selector,
        select=select,
    )
    try:
        validate_vendor_config(config)
    except FirmwareLookupError as exc:
        return CommandResult(text=str(exc), ephemeral=True)
    services.vendor_config_repo.upsert(config)
    return CommandResult(text=f"Version check config saved: {vendor}")
```

In `handle_lookup_firmware`, pass the HTTP adapter and make Download conditional. Replace the `FirmwareLookupService(...)` construction:

```python
    lookup = FirmwareLookupService(
        services.target_repo,
        services.vendor_config_repo,
        services.browser,
        services.http,
    )
```

Replace the final `lines = [...]` block:

```python
    lines = [
        f"Firmware lookup: {result.target_name}",
        f"Vendor: {result.vendor}",
        f"URL: {result.resolved_url}",
        f"Version: {result.version}",
    ]
    if result.download_url:
        lines.append(f"Download: {result.download_url}")
    return CommandResult(text="\n".join(lines))
```

- [ ] **Step 4: Wire the adapter and alias commands in `bot.py`**

In `src/updater/presentation/discord_bot/bot.py`, import the HTTP adapter:

```python
from updater.infrastructure.browser.cloak import CloakBrowserAdapter
from updater.infrastructure.browser.http_fetch import HttpFetchAdapter
```

In `_build_services`, add `http`:

```python
        vendor_config_repo=MongoVendorConfigRepository(db.db),
        browser=CloakBrowserAdapter(),
        http=HttpFetchAdapter(),
    )
```

Add two alias commands in `build_client` after the existing `lookup-firmware` registration (they reuse the same handlers, add the version-checker parameters):

```python
    @tree.command(name="set-version-check", description="Configure a target version checker", guild=guild)
    @app_commands.describe(
        vendor="Config name (use the target name)",
        url_template="Exact HTTPS URL to fetch",
        regex="Regex with group 1 = version",
        target="Target name to bind this checker to",
        fetch="'http' (default for release pages) or 'browser'",
        selector="Optional CSS selector",
        select="first (default), last, or max",
    )
    async def set_version_check(
        interaction: discord.Interaction,
        vendor: str,
        url_template: str,
        regex: str,
        target: str | None = None,
        fetch: str = "http",
        selector: str | None = None,
        select: str = "first",
    ):
        if not await _admin_only(interaction):
            return
        await _reply(
            interaction,
            await cmd.handle_set_vendor_firmware(
                services, vendor=vendor, url_template=url_template, attr_id="",
                regex=regex, target=target, fetch=fetch, selector=selector, select=select,
            ),
        )

    @tree.command(name="check-version", description="Check a target's current version", guild=guild)
    @app_commands.describe(target_id="Target number from /list-targets")
    async def check_version(interaction: discord.Interaction, target_id: int):
        await _reply(interaction, await cmd.handle_lookup_firmware(services, target_id=target_id))
```

- [ ] **Step 5: Run the Discord tests**

Run: `python -m pytest tests/presentation/discord_bot/test_commands.py -v`
Expected: PASS — new tests pass and existing lookup/import/set tests still pass (the default `FakeHttpAdapter` covers `Services.http`).

- [ ] **Step 6: Commit**

```bash
git add src/updater/presentation/discord_bot/commands.py src/updater/presentation/discord_bot/bot.py tests/presentation/discord_bot/test_commands.py
git commit -m "feat: expose version checkers via Discord set-version-check/check-version"
```

---

### Task 9: Documentation and full verification

**Files:**
- Modify: `README.md` (Usage section)
- Test: full suite

- [ ] **Step 1: Document the version checkers**

In `README.md`, after the "Vendor firmware configuration and lookup" section, add:

```markdown
### Target version checkers

Ten Pwn2Own targets ship on-demand version checkers that read each vendor's
release/changelog page directly. Seed them into MongoDB:

    version-config seed

Then check a target's current version by its `/list-targets` number:

    version-lookup --target-id 7

Each checker is a `VendorConfig` bound to a target with `fetch=http`, an exact
URL, a `select` strategy (`first`/`last`/`max`), and a regex whose first group
is the version. Add or override one with:

    version-config add --vendor Chroma --target Chroma \
      --url-template https://github.com/chroma-core/chroma/releases \
      --fetch http --select first \
      --regex 'releases/tag/(\d+\.\d+\.\d+)(?=["/#?])'

On Discord: `/set-version-check` and `/check-version`.
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS (all tasks green).

- [ ] **Step 3: Inspect the diff**

Run: `git diff --stat HEAD~8`
Expected: changes confined to `domain/models.py`, `application/firmware_lookup.py`, `infrastructure/{mongo.py,browser/*,seed/*}`, `domain/repositories.py`, `cli/*`, `presentation/discord_bot/{commands.py,bot.py}`, `pyproject.toml`, `samples/version_checks.csv`, `tests/*`, `README.md`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document target version checkers"
```

---

## Self-Review

**Spec coverage:**
- Model extension (`target`/`fetch`/`selector`/`select`, relaxed validation) → Task 1.
- Mongo mapping/index + `find_by_target` → Task 2.
- `HttpFetchAdapter` → Task 3. (Browser-selector generalization is intentionally deferred: all ten targets are server-rendered and use `http`; the legacy `fetch_element_html` path is untouched. Noted as a scope trim vs. the spec, which listed browser-selector generalization as in-scope — flagged here rather than silently dropped.)
- Lookup service: per-target resolution, fetch selection, `select` first/last/max, optional download → Task 4.
- CLI flags + `version-*` aliases → Task 5.
- CSV importer columns + sample → Task 6.
- Ten seed configs + per-target fixtures + `vendor-config seed` → Task 7.
- Discord optional params + `/set-version-check`, `/check-version` → Task 8.
- Docs → Task 9.

**Placeholder scan:** No TBD/TODO; every code step is complete. Fixtures and regexes are concrete and mutually validated in Task 7.

**Type consistency:** `VendorConfig` field names (`target`, `fetch`, `selector`, `select`) are identical across Tasks 1, 2, 5, 6, 7, 8. `find_by_target(target)` signature matches between the protocol (Task 2), the Mongo repo (Task 2), and the fakes (Tasks 4, 8). `FirmwareLookupService(..., http=None)` and `FirmwareLookupResult.download_url: str | None` are consistent across Tasks 4, 5, 8. `_select_match(regex, html, select)` is defined in Task 4 and reused in Task 7.

**Intentional existing-test changes (behavior changes, not silent edits):**
- Task 1: `test_validate_vendor_config_rejects_bad_config` split/rewritten — `{alias}` now optional, ≥1 group.
- Task 5: `test_vendor_config_add_rejects_invalid_regex` now uses a truly invalid regex (`(.+)` became valid).
- Task 8: `test_set_vendor_firmware_rejects_missing_alias_placeholder` replaced — fixed URLs without `{alias}` are now valid.
