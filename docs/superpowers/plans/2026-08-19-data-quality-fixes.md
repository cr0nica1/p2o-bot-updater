# Data Quality Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop missing real CVEs, stop storing junk Chroma hits, make incremental NVD sync work, and stop recording Samsung’s global SMR as Galaxy S26 firmware.

**Architecture:** Fix NVD date windows in `NvdSource`. Give `Target` an explicit `search_names` list so generic display names (Chroma) are not used as NVD queries. Expand seed aliases/vendors and drop the Samsung S26 checker. Add a purge use case that unlinks Chroma links whose advisory text is not ChromaDB. Re-seed + targeted `sync_one` repairs live Mongo.

**Tech Stack:** Python 3.12, pytest, pymongo, requests, existing Discord bot. Run tests with `.venv/bin/python -m pytest`. Spec/audit: `docs/2026-08-19-data-quality-audit.md`.

**Already done (do not redo):** brief daily Discord notify (`build_summary_message` / `_run_notify`). That is out of scope.

---

## Problems this plan closes

| ID | Problem | Fix |
|---|---|---|
| P1 | Incremental NVD `pubStartDate` without `pubEndDate` → HTTP 404 for any target that already has a 2026 CVE | Send both dates in ≤120-day windows |
| P2 | Seeded targets have empty `aliases`; NVD exact-match on the long official name misses Claude Code (~44), pgvector (2 real), Hue Bridge (8 possible) | Seed aliases + `search_names`; update `samples/targets.csv` |
| P3 | Searching `"Chroma"` stores ~17 FFmpeg/Razer/ChromeOS false positives | `search_names=["ChromaDB"]` + purge existing junk links |
| P4 | Samsung S26 “latest version” is the global SMR bulletin (page has no S26) | Remove that checker; delete stored SMR rows |
| P5 | `version-config seed` `$set`s `aliases=[]` and does not include Oura | Seed full Target records; add Oura; do not wipe aliases |
| P6 | pgvector GitHub HTML 429 | Point checker at `raw.githubusercontent.com` markdown |
| P7 | Empty leftover DB `p2o` | Operator note only (drop if unused) — no code |
| P8 | Unauthenticated NVD 5 req/30s, 30s timeouts | Optional `NVD_API_KEY`; sleep between date windows |

**Out of scope:** rewriting ZDI scraping; inventing an S26-specific firmware URL (none found); treating all “Home Assistant” Core CVEs as Green-specific beyond adding the alias.

**Decisions:**

- Hue: add alias `Philips Hue Bridge` (may attach older non-Pro CVEs; accepted).
- Home Assistant Green: add alias `Home Assistant` (Green runs HA OS; some Core CVEs will attach).
- Do **not** add aliases `Dynamo` or `codex` (too generic).
- Chroma NVD queries are **only** `ChromaDB` (`search_names` overrides name+aliases).
- Samsung stays as a CVE target with no version checker.

---

## File structure

- Modify: `src/updater/infrastructure/sources/nvd.py` — date windows, optional sleep.
- Modify: `src/updater/domain/models.py` — `Target.search_names` + `search_queries()`.
- Modify: `src/updater/infrastructure/mongo.py` — map `search_names`; `delete_link` on target-vuln links; `delete_by_target` on versions.
- Modify: `src/updater/domain/repositories.py` — those two delete methods.
- Modify: `src/updater/infrastructure/csv_loader.py` — `search_names` column.
- Modify: `src/updater/infrastructure/seed/version_checks.py` — aliases, vendors, Oura, drop Samsung checker, pgvector raw URL, seed cleanup.
- Modify: `src/updater/presentation/discord_bot/config.py` — optional `nvd_api_key`.
- Modify: `src/updater/presentation/discord_bot/bot.py` — pass API key into `NvdSource`.
- Modify: `src/updater/cli/vendor_config.py` — pass version repo into seed; add `purge-chroma` subcommand.
- Create: `src/updater/application/purge_chroma.py` — unlink non-ChromaDB Chroma links.
- Modify: `samples/targets.csv` — aliases + search_names.
- Modify: `.env.example` — `NVD_API_KEY`.
- Tests: `tests/infrastructure/sources/test_nvd.py`, `tests/domain/test_models.py`, `tests/infrastructure/test_mongo_mapping.py`, `tests/infrastructure/test_csv_loader.py`, `tests/infrastructure/test_version_check_seed.py`, `tests/application/test_purge_chroma.py` (new), `tests/cli/test_vendor_config_cli.py`, `tests/presentation/discord_bot/test_config.py`.
- Create: `tests/fixtures/version/oura.html` (minimal snippet).
- Modify: `docs/huong-dan-su-dung.md` (seed counts, Samsung, aliases).

---

### Task 1: NVD publication-date windows

**Files:**
- Modify: `src/updater/infrastructure/sources/nvd.py`
- Test: `tests/infrastructure/sources/test_nvd.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/infrastructure/sources/test_nvd.py`:

```python
from datetime import date

from updater.infrastructure.sources.nvd import NvdSource, nvd_pub_windows


def test_nvd_pub_windows_splits_into_120_day_chunks():
    windows = nvd_pub_windows(2026, today=date(2026, 8, 19))
    assert windows == [
        ("2026-01-01T00:00:00.000", "2026-04-30T23:59:59.999"),
        ("2026-05-01T00:00:00.000", "2026-08-19T23:59:59.999"),
    ]


def test_nvd_pub_windows_empty_when_year_in_future():
    assert nvd_pub_windows(2027, today=date(2026, 8, 19)) == []


def test_nvd_search_without_since_year_omits_dates():
    captured = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"vulnerabilities": []}

    def fake_get(url, **kwargs):
        captured.append(kwargs.get("params"))
        return FakeResponse()

    NvdSource(get=fake_get).search(Target(name="LiteLLM"), "LiteLLM")
    assert "pubStartDate" not in captured[0]
    assert "pubEndDate" not in captured[0]


def test_nvd_search_with_since_year_sends_start_and_end_per_window():
    captured = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"vulnerabilities": []}

    def fake_get(url, **kwargs):
        captured.append(kwargs.get("params"))
        return FakeResponse()

    NvdSource(get=fake_get).search(
        Target(name="LiteLLM"), "LiteLLM", since_year=2026, today=date(2026, 8, 19)
    )
    assert len(captured) == 2
    assert captured[0]["pubStartDate"] == "2026-01-01T00:00:00.000"
    assert captured[0]["pubEndDate"] == "2026-04-30T23:59:59.999"
    assert captured[1]["pubStartDate"] == "2026-05-01T00:00:00.000"
    assert captured[1]["pubEndDate"] == "2026-08-19T23:59:59.999"
    assert captured[0]["keywordSearch"] == "LiteLLM"
    assert "keywordExactMatch" in captured[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/infrastructure/sources/test_nvd.py::test_nvd_pub_windows_splits_into_120_day_chunks tests/infrastructure/sources/test_nvd.py::test_nvd_search_with_since_year_sends_start_and_end_per_window -v
```

Expected: FAIL (`ImportError` or `TypeError: unexpected keyword argument 'today'`).

- [ ] **Step 3: Implement windows + search**

In `src/updater/infrastructure/sources/nvd.py` add imports `date, timedelta` from datetime. Add:

```python
NVD_WINDOW_DAYS = 119


def nvd_pub_windows(since_year: int, *, today: date | None = None) -> list[tuple[str, str]]:
    today = today or date.today()
    start = date(since_year, 1, 1)
    if start > today:
        return []
    windows: list[tuple[str, str]] = []
    cursor = start
    while cursor <= today:
        end = min(cursor + timedelta(days=NVD_WINDOW_DAYS), today)
        windows.append(
            (f"{cursor.isoformat()}T00:00:00.000", f"{end.isoformat()}T23:59:59.999")
        )
        cursor = end + timedelta(days=1)
    return windows
```

Replace `NvdSource.search` with:

```python
    def search(
        self,
        _target: Target,
        query: str,
        since_year: int | None = None,
        *,
        today: date | None = None,
    ) -> list[tuple[Vulnerability, dict[str, Any]]]:
        base: dict[str, Any] = {"keywordSearch": query, "keywordExactMatch": ""}
        headers = {"apiKey": self._api_key} if self._api_key else None
        windows = nvd_pub_windows(since_year, today=today) if since_year is not None else [None]
        results: list[tuple[Vulnerability, dict[str, Any]]] = []
        for index, window in enumerate(windows):
            if index and self._pause:
                self._pause(0.6 if self._api_key else 6.0)
            params = dict(base)
            if window is not None:
                params["pubStartDate"], params["pubEndDate"] = window
            results.extend(self._hits(params, headers, query))
        return results

    def _hits(self, params, headers, query):
        response = self._get(NVD_CVES_URL, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        results = []
        for item in payload.get("vulnerabilities", []):
            cleaned = strip_non_nist_cvss_metrics(strip_cpe_from_raw(item))
            vulnerability = normalize_nvd_item(cleaned)
            results.append((vulnerability, {"query": query, "nvd": cleaned}))
        return results
```

In `__init__`, set `self._pause = None` when `get` is injected, else `time.sleep`:

```python
    def __init__(self, *, get=None, api_key=None, pause=None):
        self._get = get or requests.get
        self._api_key = api_key
        if pause is not None:
            self._pause = pause
        elif get is None:
            import time
            self._pause = time.sleep
        else:
            self._pause = None
```

Existing `test_nvd_source_evidence_excludes_cpe_configurations` must still pass (no `since_year`).

- [ ] **Step 4: Run NVD tests**

```bash
.venv/bin/python -m pytest tests/infrastructure/sources/test_nvd.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/infrastructure/sources/nvd.py tests/infrastructure/sources/test_nvd.py
git commit -m "fix: NVD incremental sync sends pubEndDate in 120-day windows"
```

---

### Task 2: Optional `NVD_API_KEY`

**Files:**
- Modify: `src/updater/presentation/discord_bot/config.py`
- Modify: `src/updater/presentation/discord_bot/bot.py`
- Modify: `.env.example`
- Test: `tests/presentation/discord_bot/test_config.py`

- [ ] **Step 1: Write the failing test**

In `tests/presentation/discord_bot/test_config.py`, after the existing load-success test, add:

```python
def test_load_config_reads_optional_nvd_api_key(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=tok\nDISCORD_GUILD_ID=111\nDISCORD_CHANNEL_ID=222\n"
        "DISCORD_ADMIN_ROLE_ID=333\nSYNC_TIME=08:00\nNOTIFY_TIME=09:30\n"
        "NVD_API_KEY=nvd-secret\n"
    )
    config = load_config(env_file)
    assert config.nvd_api_key == "nvd-secret"


def test_load_config_nvd_api_key_defaults_none(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=tok\nDISCORD_GUILD_ID=111\nDISCORD_CHANNEL_ID=222\n"
        "DISCORD_ADMIN_ROLE_ID=333\nSYNC_TIME=08:00\nNOTIFY_TIME=09:30\n"
    )
    config = load_config(env_file)
    assert config.nvd_api_key is None
```

- [ ] **Step 2: Run to verify FAIL**

```bash
.venv/bin/python -m pytest tests/presentation/discord_bot/test_config.py::test_load_config_reads_optional_nvd_api_key -v
```

Expected: FAIL `BotConfig has no attribute nvd_api_key` or unexpected keyword.

- [ ] **Step 3: Implement**

Add `nvd_api_key: str | None = None` to `BotConfig`. In `load_config` return:

```python
        nvd_api_key=(values.get("NVD_API_KEY") or "").strip() or None,
```

In `bot.py` `_build_services`:

```python
        sources=[NvdSource(api_key=config.nvd_api_key), ZdiSource()],
```

`.env.example` add:

```
NVD_API_KEY=
```

Do not put a real key in the repo. Do not print the key in logs.

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/presentation/discord_bot/test_config.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/presentation/discord_bot/config.py src/updater/presentation/discord_bot/bot.py .env.example tests/presentation/discord_bot/test_config.py
git commit -m "feat: optional NVD_API_KEY for authenticated NVD requests"
```

---

### Task 3: `Target.search_names` overrides NVD/ZDI queries

**Files:**
- Modify: `src/updater/domain/models.py`
- Test: `tests/domain/test_models.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_search_queries_use_search_names_when_set():
    target = Target(name="Chroma", aliases=["unused"], search_names=["ChromaDB"])
    assert target.search_queries() == ["ChromaDB"]


def test_search_queries_fall_back_to_name_and_aliases():
    target = Target(name="LiteLLM", aliases=["litellm"])
    assert target.search_queries() == ["LiteLLM", "litellm"]
```

Keep `test_target_search_queries_include_name_and_unique_aliases` as the fallback case.

- [ ] **Step 2: Run to verify FAIL**

```bash
.venv/bin/python -m pytest tests/domain/test_models.py::test_search_queries_use_search_names_when_set -v
```

Expected: FAIL `unexpected keyword argument 'search_names'`.

- [ ] **Step 3: Implement**

On `Target`:

```python
    search_names: list[str] = field(default_factory=list)
```

```python
    def search_queries(self) -> list[str]:
        if self.search_names:
            return _unique_non_empty(self.search_names)
        return _unique_non_empty([self.name, *self.aliases])
```

- [ ] **Step 4: Run domain tests**

```bash
.venv/bin/python -m pytest tests/domain/test_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/domain/models.py tests/domain/test_models.py
git commit -m "feat: Target.search_names overrides CVE search queries"
```

---

### Task 4: Persist `search_names` (Mongo + CSV)

**Files:**
- Modify: `src/updater/infrastructure/mongo.py` (`target_to_document` / `target_from_document`)
- Modify: `src/updater/infrastructure/csv_loader.py` (`KNOWN_COLUMNS`, loader)
- Test: `tests/infrastructure/test_mongo_mapping.py`, `tests/infrastructure/test_csv_loader.py`

- [ ] **Step 1: Write failing tests**

```python
def test_target_document_round_trips_search_names():
    target = Target(name="Chroma", search_names=["ChromaDB"])
    document = target_to_document(target)
    assert document["search_names"] == ["ChromaDB"]
    loaded = target_from_document({**document, "_id": "x", "created_at": target.created_at, "updated_at": target.updated_at})
    assert loaded.search_names == ["ChromaDB"]
```

```python
def test_loads_search_names_semicolon_list(tmp_path: Path):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text(
        "name,aliases,search_names\nChroma,,ChromaDB\n",
        encoding="utf-8",
    )
    rows = CsvTargetLoader().load(csv_path)
    assert rows.items[0].target.search_names == ["ChromaDB"]
```

- [ ] **Step 2: Run to verify FAIL**

```bash
.venv/bin/python -m pytest tests/infrastructure/test_mongo_mapping.py::test_target_document_round_trips_search_names tests/infrastructure/test_csv_loader.py::test_loads_search_names_semicolon_list -v
```

Expected: FAIL (missing key / empty list).

- [ ] **Step 3: Implement**

`target_to_document`: add `"search_names": list(target.search_names)`.
`target_from_document`: `search_names=list(document.get("search_names", []))`.

`KNOWN_COLUMNS` add `"search_names"`. When constructing `Target`, `search_names=_split_aliases(row.get("search_names"))` (same semicolon split as aliases).

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/infrastructure/test_mongo_mapping.py tests/infrastructure/test_csv_loader.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/infrastructure/mongo.py src/updater/infrastructure/csv_loader.py tests/infrastructure/test_mongo_mapping.py tests/infrastructure/test_csv_loader.py
git commit -m "feat: persist Target.search_names in Mongo and CSV"
```

---

### Task 5: Seed aliases, Oura, drop Samsung checker, pgvector raw URL

**Files:**
- Modify: `src/updater/infrastructure/seed/version_checks.py`
- Modify: `samples/targets.csv`
- Create: `tests/fixtures/version/oura.html`
- Test: `tests/infrastructure/test_version_check_seed.py`

Replace seed data so **targets and checkers are separate**. Samsung remains a target with no checker. Oura is a target **and** a checker.

- [ ] **Step 1: Write failing tests** (update existing seed tests)

Replace `EXPECTED` / counts in `tests/infrastructure/test_version_check_seed.py`:

```python
EXPECTED = {
    "Philips Hue Bridge Pro": ("philips.html", "2071401010"),
    "Home Assistant Green": ("home_assistant.html", "18.2"),
    "OpenAI Codex": ("codex.html", "0.147.0"),
    "Anthropic Claude Code": ("claude_code.html", "2.1.233"),
    "Postgres pgvector": ("pgvector.html", "0.8.6"),
    "Oracle Autonomous AI Database": ("oracle.html", "23.26.3"),
    "LiteLLM": ("litellm.html", "v1.97.0"),
    "NVIDIA Dynamo": ("dynamo.html", "v1.4.0"),
    "Chroma": ("chroma.html", "1.5.9"),
    "Oura Ring 5": ("oura.html", "2.1.3"),
}

TARGET_NAMES = {
    *EXPECTED,
    "Samsung Galaxy S26",
}


def test_seed_covers_eleven_targets_and_ten_checkers():
    assert len(version_checks()) == 10
    assert {t.name for t in targets()} == TARGET_NAMES
    assert "Samsung Galaxy S26" not in {c.target for c in version_checks()}


def test_chroma_search_names_are_chromadb_only():
    chroma = next(t for t in targets() if t.name == "Chroma")
    assert chroma.search_queries() == ["ChromaDB"]


def test_claude_and_pgvector_aliases():
    by_name = {t.name: t for t in targets()}
    assert "Claude Code" in by_name["Anthropic Claude Code"].search_queries()
    assert "pgvector" in by_name["Postgres pgvector"].search_queries()
    assert "Philips Hue Bridge" in by_name["Philips Hue Bridge Pro"].search_queries()


def test_pgvector_checker_uses_raw_github():
    config = next(c for c in version_checks() if c.target == "Postgres pgvector")
    assert "raw.githubusercontent.com" in config.url_template
```

Parametrize regex tests over `version_checks()` as today; Samsung is gone so the old samsung fixture test will not run.

`tests/fixtures/version/oura.html` (minimal):

```html
<h2 id="h_01">Oura Ring 5 Firmware Versions</h2>
<p>2.1.3</p>
```

Regex must still match the live pattern from the audit:

```
h2 id=[\s\S]{0,80}?Oura Ring 5 Firmware Versions[\s\S]{0,200}?(\d+\.\d+\.\d+)
```

The fixture above satisfies that.

- [ ] **Step 2: Run to verify FAIL**

```bash
.venv/bin/python -m pytest tests/infrastructure/test_version_check_seed.py -v
```

Expected: FAIL (still 10 targets including Samsung, no Oura, Chroma queries are `["Chroma"]`).

- [ ] **Step 3: Rewrite seed module**

`src/updater/infrastructure/seed/version_checks.py`:

```python
from updater.domain.models import Target, VendorConfig

# (name, aliases, vendor, category, search_names)
_TARGETS = [
    ("Philips Hue Bridge Pro", ["philips hue bridge", "Philips Hue Bridge"], "Signify", "Smart Home", []),
    ("Samsung Galaxy S26", ["samsung galaxy s26"], "Samsung", "Mobile Phone", []),
    ("Home Assistant Green", ["Home Assistant"], "Nabu Casa", "Smart Home", []),
    ("Oura Ring 5", [], "Oura", "Wellness", []),
    ("Chroma", [], "Open Source", "AI infrastructure", ["ChromaDB"]),
    ("Postgres pgvector", ["pgvector"], "Open Source", "AI infrastructure", []),
    ("Oracle Autonomous AI Database", [], "Oracle", "AI infrastructure", []),
    ("LiteLLM", ["litellm"], "Open Source", "AI infrastructure", []),
    ("NVIDIA Dynamo", [], "NVIDIA", "AI infrastructure", []),
    ("Anthropic Claude Code", ["Claude Code", "claude code"], "Anthropic", "Coding Agent", []),
    ("OpenAI Codex", [], "OpenAI", "Coding Agent", []),
]

# (target_name, url, select, regex)
_CHECKS = [
    ("Philips Hue Bridge Pro",
     "https://www.philips-hue.com/en-us/support/release-notes/bridge-pro",
     "first", r"Software version\s+(\d{10})"),
    ("Home Assistant Green",
     "https://github.com/home-assistant/operating-system/releases",
     "first", r'releases/tag/(\d+\.\d+(?:\.\d+)?)"'),
    ("OpenAI Codex",
     "https://learn.chatgpt.com/docs/changelog?type=codex-cli",
     "first", r"@openai/codex@(\d+\.\d+\.\d+)"),
    ("Anthropic Claude Code",
     "https://code.claude.com/docs/en/changelog",
     "first", r'data-component-part="update-label"[^>]*>\s*(\d+\.\d+\.\d+)'),
    ("Postgres pgvector",
     "https://raw.githubusercontent.com/pgvector/pgvector/master/CHANGELOG.md",
     "first", r"##\s+(\d+\.\d+\.\d+)\s+\(\d{4}-\d{2}-\d{2}\)"),
    ("Oracle Autonomous AI Database",
     "https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/autonomous-ai-database-updates.html",
     "max", r"(?:Release Update\s+|release-update-)(\d+(?:\.\d+){1,2})"),
    ("LiteLLM",
     "https://docs.litellm.ai/release_notes/",
     "first", r'id="?latest-release"?[\s\S]*?/release_notes/(v\d+\.\d+\.\d+)/'),
    ("NVIDIA Dynamo",
     "https://docs.nvidia.com/dynamo/reference/releases",
     "first", r"Latest\s*\((v\d+\.\d+\.\d+)\)"),
    ("Chroma",
     "https://github.com/chroma-core/chroma/releases",
     "first", r'releases/tag/(\d+\.\d+\.\d+)(?=["/#?])'),
    ("Oura Ring 5",
     "https://support.ouraring.com/hc/en-us/articles/34036777934227-Oura-Device-Firmware-Versions",
     "first", r"h2 id=[\s\S]{0,80}?Oura Ring 5 Firmware Versions[\s\S]{0,200}?(\d+\.\d+\.\d+)"),
]


def targets() -> list[Target]:
    return [
        Target(name=name, aliases=list(aliases), vendor=vendor, category=category, search_names=list(search_names))
        for name, aliases, vendor, category, search_names in _TARGETS
    ]


def version_checks() -> list[VendorConfig]:
    return [
        VendorConfig(vendor=name, target=name, url_template=url, fetch="http", selector=None, select=select, regex=regex)
        for name, url, select, regex in _CHECKS
    ]


def seed(target_repo, vendor_config_repo, version_repo=None) -> dict[str, int]:
    for target in targets():
        target_repo.upsert(target)
    for config in version_checks():
        vendor_config_repo.upsert(config)
    vendor_config_repo.delete("Samsung Galaxy S26")
    samsung = target_repo.find_by_name("Samsung Galaxy S26")
    if samsung is not None and version_repo is not None:
        version_repo.delete_by_target(samsung.storage_id)
    return {"targets": len(_TARGETS), "configs": len(_CHECKS)}
```

`samples/targets.csv`:

```csv
name,aliases,vendor,category,search_names,version,version_type
Samsung Galaxy S26,samsung galaxy s26,Samsung,Mobile Phone,,,
Philips Hue Bridge Pro,philips hue bridge;Philips Hue Bridge,Signify,Smart Home,,,
Home Assistant Green,Home Assistant,Nabu Casa,Smart Home,,,
Oura Ring 5,,Oura,Wellness,,,
Chroma,,Open Source,AI infrastructure,ChromaDB,,
Postgres pgvector,pgvector,Open Source,AI infrastructure,,,
Oracle Autonomous AI Database,,Oracle,AI infrastructure,,,
LiteLLM,litellm,Open Source,AI infrastructure,,,
NVIDIA Dynamo,,NVIDIA,AI infrastructure,,,
Anthropic Claude Code,Claude Code;claude code,Anthropic,Coding Agent,,,
OpenAI Codex,,OpenAI,Coding Agent,,,
```

Update `test_seed_upserts_targets_and_configs` expected counts to `{"targets": 11, "configs": 10}`.

Fake `_Repo` used by that test has no `find_by_name` / `delete`. Extend it:

```python
class _Repo:
    def __init__(self):
        self.items = []

    def upsert(self, item):
        self.items.append(item)
        return item

    def find_by_name(self, name):
        return next((i for i in self.items if getattr(i, "name", None) == name), None)

    def delete(self, vendor):
        before = len(self.items)
        self.items = [i for i in self.items if getattr(i, "vendor", None) != vendor]
        return before != len(self.items)

    def delete_by_target(self, target_id):
        return 0
```

- [ ] **Step 4: Run seed tests**

```bash
.venv/bin/python -m pytest tests/infrastructure/test_version_check_seed.py tests/fixtures/version -q
```

Expected: PASS. If Oura regex fails, adjust fixture (not the live regex) until group 1 is `2.1.3`. pgvector fixture is still markdown-shaped so the same regex works against `pgvector.html`.

- [ ] **Step 5: Commit**

```bash
git add src/updater/infrastructure/seed/version_checks.py samples/targets.csv tests/infrastructure/test_version_check_seed.py tests/fixtures/version/oura.html
git commit -m "fix: seed aliases, ChromaDB-only search, Oura checker, drop Samsung SMR"
```

---

### Task 6: `delete_by_target` on versions + `delete_link` on target-vuln rows

Needed by seed cleanup (Samsung SMR rows) and Chroma purge. **Do not** delete all links for a vulnerability ID — a junk Chroma hit might theoretically be linked elsewhere.

**Files:**
- Modify: `src/updater/domain/repositories.py`
- Modify: `src/updater/infrastructure/mongo.py`
- Test: `tests/infrastructure/test_mongo_mapping.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/infrastructure/test_mongo_mapping.py`:

```python
def test_version_repo_delete_by_target_filters_target_id():
    class FakeColl:
        def delete_many(self, flt):
            assert flt == {"target_id": "t1"}
            return type("R", (), {"deleted_count": 2})()
    class Holder:
        target_versions = FakeColl()
    repo = MongoTargetVersionRepository(Holder())
    assert repo.delete_by_target("t1") == 2


def test_link_repo_delete_link_filters_pair():
    class FakeColl:
        def delete_many(self, flt):
            assert flt == {"target_id": "c1", "vulnerability_id": "j1"}
            return type("R", (), {"deleted_count": 1})()
    class Holder:
        target_vulnerabilities = FakeColl()
    repo = MongoTargetVulnerabilityRepository(Holder())
    assert repo.delete_link("c1", "j1") == 1
```

- [ ] **Step 2: Run to verify FAIL**

```bash
.venv/bin/python -m pytest tests/infrastructure/test_mongo_mapping.py::test_version_repo_delete_by_target_filters_target_id tests/infrastructure/test_mongo_mapping.py::test_link_repo_delete_link_filters_pair -v
```

Expected: FAIL `has no attribute delete_by_target` / `delete_link`.

- [ ] **Step 3: Implement**

Protocol:

```python
class TargetVersionRepository(Protocol):
    ...
    def delete_by_target(self, target_id: str) -> int: ...

class TargetVulnerabilityRepository(Protocol):
    ...
    def delete_link(self, target_id: str, vulnerability_id: str) -> int: ...
```

On `MongoTargetVersionRepository`:

```python
    def delete_by_target(self, target_id: str) -> int:
        return self.collection.delete_many({"target_id": target_id}).deleted_count
```

On `MongoTargetVulnerabilityRepository`:

```python
    def delete_link(self, target_id: str, vulnerability_id: str) -> int:
        return self.collection.delete_many(
            {"target_id": target_id, "vulnerability_id": vulnerability_id}
        ).deleted_count
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/infrastructure/test_mongo_mapping.py tests/infrastructure/test_target_version_repo.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/domain/repositories.py src/updater/infrastructure/mongo.py tests/infrastructure/test_mongo_mapping.py
git commit -m "feat: delete versions by target and a single target-vuln link"
```

---

### Task 7: Purge Chroma false positives

**Files:**
- Create: `src/updater/application/purge_chroma.py`
- Create: `tests/application/test_purge_chroma.py`

Keep a ChromaDB link if the vulnerability description or advisory_id matches `(?i)chromadb|chroma-core|chroma db`. Unlink the rest from the Chroma target. Delete a vulnerability only when **no links remain**.

- [ ] **Step 1: Write failing tests**

```python
from updater.application.purge_chroma import PurgeChromaService
from updater.domain.models import Target, TargetVulnerability, Vulnerability


class FakeTargets:
    def __init__(self, targets):
        self.targets = targets
    def find_by_name(self, name):
        return next((t for t in self.targets if t.name.lower() == name.lower()), None)
    def list_all(self):
        return list(self.targets)


class FakeVulns:
    def __init__(self, items):
        self.items = {v.id: v for v in items}
    def list_all(self):
        return list(self.items.values())
    def delete(self, vid):
        for key, v in list(self.items.items()):
            if v.id == vid or v.advisory_id == vid:
                del self.items[key]
                return True
        return False


class FakeLinks:
    def __init__(self, links):
        self.links = list(links)
    def list_all(self):
        return list(self.links)
    def delete_link(self, target_id, vulnerability_id):
        before = len(self.links)
        self.links = [
            link for link in self.links
            if not (link.target_id == target_id and link.vulnerability_id == vulnerability_id)
        ]
        return before - len(self.links)


def test_purge_unlinks_ffmpeg_chroma_keeps_chromadb():
    chroma = Target(id="c1", name="Chroma")
    keep = Vulnerability(id="k1", advisory_id="CVE-2026-8828", description="ChromaDB Rust project")
    junk = Vulnerability(id="j1", advisory_id="CVE-2012-0851", description="libavcodec chroma format")
    links = FakeLinks([
        TargetVulnerability(target_id="c1", target_name="Chroma", vulnerability_id="k1"),
        TargetVulnerability(target_id="c1", target_name="Chroma", vulnerability_id="j1"),
    ])
    vulns = FakeVulns([keep, junk])
    result = PurgeChromaService(FakeTargets([chroma]), vulns, links).run()
    assert result.unlinked == 1
    assert result.deleted_vulnerabilities == 1
    assert [l.vulnerability_id for l in links.links] == ["k1"]
    assert "j1" not in vulns.items
    assert "k1" in vulns.items


def test_purge_does_not_delete_vuln_still_linked_elsewhere():
    chroma = Target(id="c1", name="Chroma")
    shared = Vulnerability(id="s1", advisory_id="CVE-2012-0851", description="chroma format")
    links = FakeLinks([
        TargetVulnerability(target_id="c1", target_name="Chroma", vulnerability_id="s1"),
        TargetVulnerability(target_id="other", target_name="Other", vulnerability_id="s1"),
    ])
    vulns = FakeVulns([shared])
    PurgeChromaService(FakeTargets([chroma]), vulns, links).run()
    remaining = {(l.target_id, l.vulnerability_id) for l in links.links}
    assert remaining == {("other", "s1")}
    assert "s1" in vulns.items
```

- [ ] **Step 2: Run to verify FAIL**

```bash
.venv/bin/python -m pytest tests/application/test_purge_chroma.py -v
```

Expected: FAIL `ImportError`.

- [ ] **Step 3: Implement**

`src/updater/application/purge_chroma.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass

from updater.domain.models import Target

_KEEP = re.compile(r"chromadb|chroma-core|chroma db", re.I)
_CHROMA_NAME = "chroma"


@dataclass
class PurgeChromaResult:
    unlinked: int = 0
    deleted_vulnerabilities: int = 0


class PurgeChromaService:
    def __init__(self, target_repo, vulnerability_repo, link_repo) -> None:
        self.target_repo = target_repo
        self.vulnerability_repo = vulnerability_repo
        self.link_repo = link_repo

    def run(self) -> PurgeChromaResult:
        target = self.target_repo.find_by_name("Chroma")
        if target is None:
            return PurgeChromaResult()
        target_id = target.storage_id
        vulns = {v.id: v for v in self.vulnerability_repo.list_all() if v.id}
        for v in list(vulns.values()):
            vulns[v.advisory_id] = v
        result = PurgeChromaResult()
        chroma_junk_ids: set[str] = set()
        for link in self.link_repo.list_all():
            if link.target_id != target_id and (link.target_name or "").casefold() != _CHROMA_NAME:
                continue
            vuln = vulns.get(link.vulnerability_id)
            if vuln is None:
                continue
            blob = f"{vuln.advisory_id} {vuln.description or ''}"
            if _KEEP.search(blob):
                continue
            result.unlinked += self.link_repo.delete_link(target_id, link.vulnerability_id)
            chroma_junk_ids.add(link.vulnerability_id)

        remaining = {link.vulnerability_id for link in self.link_repo.list_all()}
        for vid in chroma_junk_ids:
            if vid not in remaining:
                if self.vulnerability_repo.delete(vid):
                    result.deleted_vulnerabilities += 1
        return result
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/application/test_purge_chroma.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/application/purge_chroma.py src/updater/domain/repositories.py src/updater/infrastructure/mongo.py tests/application/test_purge_chroma.py
git commit -m "feat: purge Chroma links that are not ChromaDB"
```

---

### Task 8: CLI — seed uses version repo; `purge-chroma`

**Files:**
- Modify: `src/updater/cli/vendor_config.py`
- Test: `tests/cli/test_vendor_config_cli.py`

- [ ] **Step 1: Write failing tests**

Read existing `test_vendor_config_cli.py` and add:

```python
def test_seed_passes_version_repo(monkeypatch):
    captured = {}

    def fake_seed(target_repo, vendor_repo, version_repo=None):
        captured["version_repo"] = version_repo
        return {"targets": 11, "configs": 10}

    monkeypatch.setattr("updater.infrastructure.seed.version_checks.seed", fake_seed)
    # invoke main(["seed"], ...) the same way other tests construct mongo — follow existing seed test if any.
```

If there is no seed CLI test, add one that monkeypatches `_build_repo` / `seed` and asserts stdout `Seeded 11 targets and 10 version checks.`

```python
def test_purge_chroma_prints_counts(monkeypatch):
    class Result:
        unlinked = 17
        deleted_vulnerabilities = 17
    monkeypatch.setattr(
        "updater.application.purge_chroma.PurgeChromaService.run",
        lambda self: Result(),
    )
    # main(["purge-chroma"]) → stdout contains unlinked=17
```

Follow the file’s existing monkeypatch style for Mongo.

- [ ] **Step 2: Run to verify FAIL**

```bash
.venv/bin/python -m pytest tests/cli/test_vendor_config_cli.py -k "seed or purge" -v
```

Expected: FAIL (unknown subcommand `purge-chroma` or seed message still says 10 and 10).

- [ ] **Step 3: Implement CLI**

`build_parser`: `subparsers.add_parser("purge-chroma")`.

`_build_db(env_path)` returning `MongoDatabase`. Seed branch:

```python
        if args.command == "seed":
            from updater.infrastructure.mongo import MongoDatabase, MongoTargetRepository, MongoTargetVersionRepository, MongoVendorConfigRepository
            from updater.infrastructure.seed.version_checks import seed as seed_version_checks
            config = load_config(Path(args.env))
            db = MongoDatabase(uri=config.mongodb_uri, database=config.mongodb_database)
            counts = seed_version_checks(
                MongoTargetRepository(db.db),
                MongoVendorConfigRepository(db.db),
                MongoTargetVersionRepository(db.db),
            )
            print(f"Seeded {counts['targets']} targets and {counts['configs']} version checks.")
            return 0
        if args.command == "purge-chroma":
            from updater.application.purge_chroma import PurgeChromaService
            from updater.infrastructure.mongo import (
                MongoDatabase, MongoTargetRepository,
                MongoTargetVulnerabilityRepository, MongoVulnerabilityRepository,
            )
            config = load_config(Path(args.env))
            db = MongoDatabase(uri=config.mongodb_uri, database=config.mongodb_database)
            result = PurgeChromaService(
                MongoTargetRepository(db.db),
                MongoVulnerabilityRepository(db.db),
                MongoTargetVulnerabilityRepository(db.db),
            ).run()
            print(f"Chroma purge: unlinked={result.unlinked} deleted_vulnerabilities={result.deleted_vulnerabilities}")
            return 0
```

- [ ] **Step 4: Run CLI tests + seed tests**

```bash
.venv/bin/python -m pytest tests/cli/test_vendor_config_cli.py tests/infrastructure/test_version_check_seed.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/updater/cli/vendor_config.py tests/cli/test_vendor_config_cli.py
git commit -m "feat: version-config seed repairs Samsung rows; add purge-chroma"
```

---

### Task 9: Docs

**Files:**
- Modify: `docs/huong-dan-su-dung.md`
- Modify: `README.md` (seed / aliases / NVD_API_KEY one paragraph)

- [ ] **Step 1: Update usage doc**

In `docs/huong-dan-su-dung.md`:

- Seed message: 11 targets, 10 checkers.
- Samsung has **no** version checker; `/check-version` will report no config; daily scan skips it.
- Chroma NVD query is `ChromaDB` only.
- After deploy: `version-config seed` then `version-config purge-chroma` then Discord `/sync-cves` (or a one-target sync) for Claude Code, pgvector, Hue, Home Assistant.
- Optional `NVD_API_KEY` in `.env`.
- Remove any line that says attach `samples/version_checks.csv` as vendor-firmware for the 10 original checkers if it still lists Samsung SMR.

README: under Target version checkers, note 11 targets / 10 checkers and `NVD_API_KEY`.

- [ ] **Step 2: Commit**

```bash
git add docs/huong-dan-su-dung.md README.md
git commit -m "docs: seed counts, Samsung checker removal, NVD_API_KEY"
```

---

### Task 10: Live repair (operator, after code is merged)

Not a unit test. Run against `pwn2own_updater` from `.env`.

- [ ] **Step 1: Re-seed**

```bash
.venv/bin/python -m updater.cli.vendor_config seed --env .env
```

Expected: `Seeded 11 targets and 10 version checks.`

- [ ] **Step 2: Purge Chroma junk**

```bash
.venv/bin/python -m updater.cli.vendor_config purge-chroma --env .env
```

Expected: `unlinked` around 17, `deleted_vulnerabilities` around 17 (shared-link case may delete fewer vulns).

- [ ] **Step 3: Confirm Samsung**

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from updater.presentation.discord_bot.config import load_config
from updater.infrastructure.mongo import MongoDatabase, MongoVendorConfigRepository, MongoTargetVersionRepository, MongoTargetRepository
c = load_config(Path(".env"))
db = MongoDatabase(c.mongodb_uri, c.mongodb_database)
t = MongoTargetRepository(db.db).find_by_name("Samsung Galaxy S26")
print("target", t.name if t else None)
print("checker", MongoVendorConfigRepository(db.db).find_by_target(t) if t else None)
print("versions", MongoTargetVersionRepository(db.db).find_latest(t.storage_id) if t else None)
PY
```

Expected: target exists, checker `None`, latest version `None`.

- [ ] **Step 4: Confirm Chroma queries and leftover junk**

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from updater.presentation.discord_bot.config import load_config
from updater.infrastructure.mongo import MongoDatabase, MongoTargetRepository, MongoVulnerabilityRepository, MongoTargetVulnerabilityRepository
c = load_config(Path(".env"))
db = MongoDatabase(c.mongodb_uri, c.mongodb_database)
t = MongoTargetRepository(db.db).find_by_name("Chroma")
print("queries", t.search_queries())
vulns = {str(v.id): v for v in MongoVulnerabilityRepository(db.db).list_all()}
for v in list(vulns.values()):
    vulns[v.advisory_id] = v
for link in MongoTargetVulnerabilityRepository(db.db).list_all():
    if link.target_name == "Chroma":
        v = vulns.get(link.vulnerability_id)
        print(v.advisory_id if v else link.vulnerability_id, (v.description or "")[:80] if v else "")
PY
```

Expected: `queries ['ChromaDB']`. Remaining Chroma rows mention ChromaDB / chroma-core. No FFmpeg/Razer/Chromad.

- [ ] **Step 5: Re-sync high-gap targets (NVD only first)**

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from updater.presentation.discord_bot.config import load_config
from updater.infrastructure.mongo import MongoDatabase, MongoTargetRepository, MongoVulnerabilityRepository, MongoTargetVulnerabilityRepository
from updater.infrastructure.sources.nvd import NvdSource
from updater.application.sync_vulnerabilities import SyncVulnerabilitiesService

c = load_config(Path(".env"))
db = MongoDatabase(c.mongodb_uri, c.mongodb_database)
sync = SyncVulnerabilitiesService(
    MongoTargetRepository(db.db),
    MongoVulnerabilityRepository(db.db),
    MongoTargetVulnerabilityRepository(db.db),
    [NvdSource(api_key=c.nvd_api_key)],
    progress=print,
)
for name in ["Anthropic Claude Code", "Postgres pgvector", "Philips Hue Bridge Pro", "Home Assistant Green", "Chroma"]:
    r = sync.sync_one(name)
    print(name, "seen", r.vulnerabilities_seen, "links", r.links_updated, "errors", r.errors)
PY
```

Use `sync_one` (no `since_year`) so the first backfill is a full keyword search. Pause if NVD 403s; set `NVD_API_KEY` if you have one.

Expected (order-of-magnitude, NVD totals move):

| Target | vulnerabilities_seen |
|---|---|
| Anthropic Claude Code | ~40+ |
| Postgres pgvector | ~6 (2 real + 4 adjacent) |
| Philips Hue Bridge Pro | ~11 |
| Home Assistant Green | ~45 |
| Chroma | ~7 |

Errors list must not contain `404`.

- [ ] **Step 6: Optional drop empty `p2o`**

```bash
.venv/bin/python -c "from pymongo import MongoClient; MongoClient('mongodb://localhost:27017').drop_database('p2o'); print('dropped p2o')"
```

Only if nothing else uses it. `.env` already points at `pwn2own_updater`.

- [ ] **Step 7: Full suite**

```bash
.venv/bin/python -m pytest -q
```

Expected: all passed.

- [ ] **Step 8: Commit nothing** (live DB only). Restart `updater-bot` so the running process loads the new `NvdSource` and seed data.

---

## Self-review

**Spec coverage (audit → task):**

| Audit item | Task |
|---|---|
| NVD 404 incremental | Task 1 |
| NVD rate limit / key | Task 2, Task 1 pause |
| Missed Claude Code / pgvector / Hue | Tasks 3–5, 10 |
| Chroma junk | Tasks 3, 5, 7, 8, 10 |
| Samsung SMR as S26 firmware | Tasks 5, 6, 8, 10 |
| Seed wiping aliases / missing Oura | Task 5 |
| pgvector GitHub 429 | Task 5 raw URL |
| Empty `p2o` | Task 10 step 6 |
| Daily notify verbosity | already shipped — excluded |

**Placeholders:** none intended. If `test_vendor_config_cli.py` has no existing seed test, Task 8 says to follow that file’s monkeypatch style rather than invent a new harness.

**Types:** `search_names: list[str]`; `nvd_pub_windows(...) -> list[tuple[str, str]]`; `PurgeChromaResult.unlinked` / `deleted_vulnerabilities`; `delete_link(target_id, vulnerability_id)`; seed returns `{"targets": 11, "configs": 10}`.
