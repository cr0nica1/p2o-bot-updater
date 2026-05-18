# Pwn2Own Target Updater Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI prototype that imports Pwn2Own targets from flexible CSV input, stores them in MongoDB, and syncs vulnerability data from NIST NVD and ZDI.

**Architecture:** Use a lightweight Clean Architecture split: domain objects are pure Python, application services coordinate work, infrastructure adapters handle MongoDB/CSV/HTTP/scraping, and CLI is a thin presentation layer. The same application services must be callable later from a Discord bot without importing CLI code.

**Tech Stack:** Python 3.10+, `pip` + `venv`, `pytest`, `requests`, `beautifulsoup4`, `pymongo`, standard-library `argparse`, MongoDB.

---

## File Structure

Create this project structure:

```text
/home/minhht21/Documents/updater/
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── samples/
│   └── targets.csv
├── src/
│   └── updater/
│       ├── __init__.py
│       ├── __main__.py
│       ├── application/
│       │   ├── __init__.py
│       │   ├── dto.py
│       │   ├── import_targets.py
│       │   ├── sync_vulnerabilities.py
│       │   └── export_json.py
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   └── repositories.py
│       ├── infrastructure/
│       │   ├── __init__.py
│       │   ├── csv_loader.py
│       │   ├── json_exporter.py
│       │   ├── mongo.py
│       │   └── sources/
│       │       ├── __init__.py
│       │       ├── nvd.py
│       │       └── zdi.py
│       └── presentation/
│           ├── __init__.py
│           └── cli.py
└── tests/
    ├── application/
    │   ├── test_export_json.py
    │   ├── test_import_targets.py
    │   └── test_sync_vulnerabilities.py
    ├── domain/
    │   └── test_models.py
    ├── infrastructure/
    │   ├── test_csv_loader.py
    │   ├── test_json_exporter.py
    │   ├── test_mongo_mapping.py
    │   └── sources/
    │       ├── test_nvd.py
    │       └── test_zdi.py
    └── presentation/
        └── test_cli.py
```

Responsibilities:

- `domain/models.py`: dataclasses and normalization helpers.
- `domain/repositories.py`: repository and source protocols only.
- `application/import_targets.py`: upsert targets and optional versions from parsed CSV rows.
- `application/sync_vulnerabilities.py`: call sources, upsert vulnerabilities, upsert target-vulnerability evidence.
- `application/export_json.py`: export repository data as JSON-compatible dictionaries.
- `infrastructure/csv_loader.py`: parse flexible CSV and map rows to domain objects.
- `infrastructure/mongo.py`: MongoDB repository implementations and index creation.
- `infrastructure/sources/nvd.py`: NVD API client and normalizer.
- `infrastructure/sources/zdi.py`: ZDI search/detail scraper and normalizer.
- `presentation/cli.py`: argparse command definitions and service wiring.

The current directory is not a git repository. Do not run commit commands unless the user explicitly initializes git first. Each task still includes a checkpoint step with exact files that would be committed after git exists.

---

### Task 1: Project scaffold and test harness

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `src/updater/__init__.py`
- Create: `src/updater/__main__.py`
- Create: `src/updater/domain/__init__.py`
- Create: `src/updater/application/__init__.py`
- Create: `src/updater/infrastructure/__init__.py`
- Create: `src/updater/infrastructure/sources/__init__.py`
- Create: `src/updater/presentation/__init__.py`
- Create: `tests/test_scaffold.py`

- [ ] **Step 1: Write the failing import test**

Create `tests/test_scaffold.py`:

```python
def test_package_imports():
    import updater

    assert updater.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_scaffold.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'updater'` or missing `__version__`.

- [ ] **Step 3: Create package metadata and dependencies**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "pwn2own-updater"
version = "0.1.0"
description = "CLI prototype for tracking Pwn2Own target vulnerabilities"
requires-python = ">=3.10"
dependencies = [
    "beautifulsoup4>=4.12.0",
    "pymongo>=4.6.0",
    "requests>=2.31.0",
]

[project.scripts]
updater = "updater.presentation.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

Create `requirements.txt`:

```text
beautifulsoup4>=4.12.0
pymongo>=4.6.0
requests>=2.31.0
```

Create `requirements-dev.txt`:

```text
-r requirements.txt
pytest>=8.0.0
```

Create `src/updater/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `src/updater/__main__.py`:

```python
from updater.presentation.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

Create these empty package marker files:

```text
src/updater/domain/__init__.py
src/updater/application/__init__.py
src/updater/infrastructure/__init__.py
src/updater/infrastructure/sources/__init__.py
src/updater/presentation/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest tests/test_scaffold.py -v
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run:

```bash
python -m pytest tests/test_scaffold.py -v
```

Expected: PASS. If the repository has been initialized with git, commit these files:

```bash
git add pyproject.toml requirements.txt requirements-dev.txt src/updater tests/test_scaffold.py
git commit -m "chore: scaffold updater package"
```

---

### Task 2: Domain models and repository/source protocols

**Files:**
- Create: `src/updater/domain/models.py`
- Create: `src/updater/domain/repositories.py`
- Create: `tests/domain/test_models.py`

- [ ] **Step 1: Write failing domain model tests**

Create `tests/domain/test_models.py`:

```python
from datetime import datetime, timezone

from updater.domain.models import (
    Target,
    TargetVersion,
    TargetVulnerability,
    Vulnerability,
    normalize_name,
)


def test_normalize_name_trims_and_lowercases_spaces():
    assert normalize_name("  Adobe   Acrobat Reader  ") == "adobe acrobat reader"


def test_target_search_queries_include_name_and_unique_aliases():
    target = Target(name="Adobe Acrobat Reader", aliases=["Adobe Reader", "Adobe Reader", ""])

    assert target.search_queries() == ["Adobe Acrobat Reader", "Adobe Reader"]


def test_zdi_vulnerability_prefers_cve_and_keeps_zdi_alias():
    vuln = Vulnerability.from_source(
        source="zdi",
        advisory_id="ZDI-CAN-12345",
        cve_id="CVE-2025-1234",
        cvss_score=9.8,
        severity="critical",
        description="Example vulnerability",
        references=["https://example.test/zdi"],
        published_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
        raw={"zdi_id": "ZDI-CAN-12345"},
    )

    assert vuln.advisory_id == "CVE-2025-1234"
    assert vuln.aliases == ["ZDI-CAN-12345"]
    assert vuln.sources == ["zdi"]


def test_target_version_allows_missing_version():
    version = TargetVersion(target_id="target-1")

    assert version.version is None
    assert version.version_type is None


def test_target_vulnerability_merges_evidence_without_duplicates():
    link = TargetVulnerability(target_id="target-1", vulnerability_id="vuln-1")

    link.add_evidence(source="nvd", matched_query="Adobe Reader", evidence={"id": "CVE-2025-1234"})
    link.add_evidence(source="nvd", matched_query="Adobe Reader", evidence={"id": "CVE-2025-1234"})
    link.add_evidence(source="zdi", matched_query="Acrobat Reader", evidence={"id": "ZDI-CAN-12345"})

    assert link.matched_queries == ["Adobe Reader", "Acrobat Reader"]
    assert [item["source"] for item in link.evidence_sources] == ["nvd", "zdi"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/domain/test_models.py -v
```

Expected: FAIL with missing `updater.domain.models`.

- [ ] **Step 3: Implement domain models**

Create `src/updater/domain/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import re


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        key = normalize_name(cleaned) if cleaned else ""
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


@dataclass
class Target:
    name: str
    aliases: list[str] = field(default_factory=list)
    vendor: str | None = None
    category: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def normalized_name(self) -> str:
        return normalize_name(self.name)

    def search_queries(self) -> list[str]:
        return _unique_non_empty([self.name, *self.aliases])


@dataclass
class TargetVersion:
    target_id: str | None = None
    version: str | None = None
    version_type: str | None = None
    release_date: datetime | None = None
    source_url: str | None = None
    is_latest: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    first_seen_at: datetime = field(default_factory=utc_now)
    last_seen_at: datetime = field(default_factory=utc_now)


@dataclass
class Vulnerability:
    advisory_id: str
    aliases: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    cvss_score: float | None = None
    severity: str | None = None
    description: str | None = None
    references: list[str] = field(default_factory=list)
    published_date: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @classmethod
    def from_source(
        cls,
        *,
        source: str,
        advisory_id: str,
        cve_id: str | None,
        cvss_score: float | None,
        severity: str | None,
        description: str | None,
        references: list[str],
        published_date: datetime | None,
        raw: dict[str, Any],
    ) -> "Vulnerability":
        canonical_id = cve_id or advisory_id
        aliases = _unique_non_empty([] if canonical_id == advisory_id else [advisory_id])
        return cls(
            advisory_id=canonical_id,
            aliases=aliases,
            sources=[source],
            cvss_score=cvss_score,
            severity=severity,
            description=description,
            references=_unique_non_empty(references),
            published_date=published_date,
            raw={source: raw},
        )


@dataclass
class TargetVulnerability:
    target_id: str
    vulnerability_id: str
    affected_versions: list[str] = field(default_factory=list)
    fixed_versions: list[str] = field(default_factory=list)
    matched_queries: list[str] = field(default_factory=list)
    evidence_sources: list[dict[str, Any]] = field(default_factory=list)
    id: str | None = None
    first_seen_at: datetime = field(default_factory=utc_now)
    last_seen_at: datetime = field(default_factory=utc_now)

    def add_evidence(self, *, source: str, matched_query: str, evidence: dict[str, Any]) -> None:
        self.matched_queries = _unique_non_empty([*self.matched_queries, matched_query])
        if not any(item.get("source") == source for item in self.evidence_sources):
            self.evidence_sources.append({"source": source, "evidence": evidence})
        self.last_seen_at = utc_now()
```

Create `src/updater/domain/repositories.py`:

```python
from __future__ import annotations

from typing import Protocol

from updater.domain.models import Target, TargetVersion, TargetVulnerability, Vulnerability


class TargetRepository(Protocol):
    def upsert(self, target: Target) -> Target: ...
    def list_all(self) -> list[Target]: ...
    def find_by_name(self, name: str) -> Target | None: ...


class TargetVersionRepository(Protocol):
    def upsert(self, version: TargetVersion) -> TargetVersion: ...


class VulnerabilityRepository(Protocol):
    def upsert(self, vulnerability: Vulnerability) -> Vulnerability: ...
    def list_all(self) -> list[Vulnerability]: ...


class TargetVulnerabilityRepository(Protocol):
    def upsert(self, link: TargetVulnerability) -> TargetVulnerability: ...
    def list_all(self) -> list[TargetVulnerability]: ...


class VulnerabilitySource(Protocol):
    source_name: str

    def search(self, target: Target, query: str) -> list[tuple[Vulnerability, dict]]: ...
```

- [ ] **Step 4: Run domain tests**

Run:

```bash
python -m pytest tests/domain/test_models.py -v
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run:

```bash
python -m pytest tests/domain/test_models.py -v
```

Expected: PASS. If git exists, commit:

```bash
git add src/updater/domain tests/domain/test_models.py
git commit -m "feat: add updater domain model"
```

---

### Task 3: Flexible CSV loader and mapping

**Files:**
- Create: `src/updater/infrastructure/csv_loader.py`
- Create: `tests/infrastructure/test_csv_loader.py`

- [ ] **Step 1: Write failing CSV loader tests**

Create `tests/infrastructure/test_csv_loader.py`:

```python
from pathlib import Path

from updater.infrastructure.csv_loader import CsvTargetLoader


def test_loads_name_only_csv(tmp_path: Path):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text("name\nAdobe Acrobat Reader\n", encoding="utf-8")

    rows = CsvTargetLoader().load(csv_path)

    assert rows.errors == []
    assert rows.items[0].target.name == "Adobe Acrobat Reader"
    assert rows.items[0].target.aliases == []
    assert rows.items[0].version is None


def test_loads_aliases_and_version(tmp_path: Path):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text(
        "name,aliases,vendor,category,version,version_type,release_date,source_url\n"
        "Adobe Acrobat Reader,Acrobat Reader;Adobe Reader,Adobe,browser,2024.005.20320,software,2024-12-01,https://example.test/release\n",
        encoding="utf-8",
    )

    rows = CsvTargetLoader().load(csv_path)

    item = rows.items[0]
    assert item.target.aliases == ["Acrobat Reader", "Adobe Reader"]
    assert item.target.vendor == "Adobe"
    assert item.target.category == "browser"
    assert item.version is not None
    assert item.version.version == "2024.005.20320"
    assert item.version.version_type == "software"
    assert item.version.source_url == "https://example.test/release"


def test_preserves_unknown_columns_as_raw_metadata(tmp_path: Path):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text("name,notes\nVMware Workstation,contest target\n", encoding="utf-8")

    rows = CsvTargetLoader().load(csv_path)

    assert rows.items[0].target.raw_metadata == {"notes": "contest target"}


def test_skips_missing_name_rows(tmp_path: Path):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text("name,aliases\n,Alias Only\nValid Target,Alias\n", encoding="utf-8")

    rows = CsvTargetLoader().load(csv_path)

    assert [item.target.name for item in rows.items] == ["Valid Target"]
    assert rows.errors == ["row 2: missing required name"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/infrastructure/test_csv_loader.py -v
```

Expected: FAIL with missing `CsvTargetLoader`.

- [ ] **Step 3: Implement CSV loader**

Create `src/updater/infrastructure/csv_loader.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import csv

from updater.domain.models import Target, TargetVersion

KNOWN_COLUMNS = {
    "name",
    "aliases",
    "vendor",
    "category",
    "version",
    "version_type",
    "release_date",
    "source_url",
}


@dataclass
class LoadedTarget:
    target: Target
    version: TargetVersion | None


@dataclass
class CsvLoadResult:
    items: list[LoadedTarget]
    errors: list[str]


class CsvTargetLoader:
    def load(self, path: str | Path) -> CsvLoadResult:
        items: list[LoadedTarget] = []
        errors: list[str] = []
        with Path(path).open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row_number, row in enumerate(reader, start=2):
                name = (row.get("name") or "").strip()
                if not name:
                    errors.append(f"row {row_number}: missing required name")
                    continue
                aliases = [part.strip() for part in (row.get("aliases") or "").split(";") if part.strip()]
                raw_metadata = {
                    key: value
                    for key, value in row.items()
                    if key not in KNOWN_COLUMNS and value not in (None, "")
                }
                target = Target(
                    name=name,
                    aliases=aliases,
                    vendor=self._clean(row.get("vendor")),
                    category=self._clean(row.get("category")),
                    raw_metadata=raw_metadata,
                )
                version_value = self._clean(row.get("version"))
                version = None
                if version_value:
                    version = TargetVersion(
                        version=version_value,
                        version_type=self._clean(row.get("version_type")),
                        release_date=self._parse_date(row.get("release_date")),
                        source_url=self._clean(row.get("source_url")),
                        raw=dict(row),
                    )
                items.append(LoadedTarget(target=target, version=version))
        return CsvLoadResult(items=items, errors=errors)

    def _clean(self, value: str | None) -> str | None:
        cleaned = (value or "").strip()
        return cleaned or None

    def _parse_date(self, value: str | None) -> datetime | None:
        cleaned = self._clean(value)
        if cleaned is None:
            return None
        return datetime.fromisoformat(cleaned).replace(tzinfo=timezone.utc)
```

- [ ] **Step 4: Run CSV tests**

Run:

```bash
python -m pytest tests/infrastructure/test_csv_loader.py -v
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run:

```bash
python -m pytest tests/domain/test_models.py tests/infrastructure/test_csv_loader.py -v
```

Expected: PASS. If git exists, commit:

```bash
git add src/updater/infrastructure/csv_loader.py tests/infrastructure/test_csv_loader.py
git commit -m "feat: load flexible target csv input"
```

---

### Task 4: Application services with fake repositories

**Files:**
- Create: `src/updater/application/dto.py`
- Create: `src/updater/application/import_targets.py`
- Create: `src/updater/application/sync_vulnerabilities.py`
- Create: `tests/application/test_import_targets.py`
- Create: `tests/application/test_sync_vulnerabilities.py`

- [ ] **Step 1: Write failing import service tests**

Create `tests/application/test_import_targets.py`:

```python
from updater.application.import_targets import ImportTargetsService
from updater.domain.models import Target, TargetVersion


class FakeTargetRepository:
    def __init__(self):
        self.targets = {}

    def upsert(self, target: Target) -> Target:
        target.id = target.id or f"target-{len(self.targets) + 1}"
        self.targets[target.normalized_name] = target
        return target

    def list_all(self):
        return list(self.targets.values())

    def find_by_name(self, name: str):
        return self.targets.get(name.strip().lower())


class FakeTargetVersionRepository:
    def __init__(self):
        self.versions = []

    def upsert(self, version: TargetVersion) -> TargetVersion:
        version.id = version.id or f"version-{len(self.versions) + 1}"
        self.versions.append(version)
        return version


def test_import_targets_upserts_target_and_version():
    target_repo = FakeTargetRepository()
    version_repo = FakeTargetVersionRepository()
    service = ImportTargetsService(target_repo, version_repo)

    result = service.import_items([
        (Target(name="Adobe Acrobat Reader"), TargetVersion(version="2024.005.20320", version_type="software"))
    ])

    assert result.targets_imported == 1
    assert result.versions_imported == 1
    assert target_repo.list_all()[0].id == "target-1"
    assert version_repo.versions[0].target_id == "target-1"


def test_import_targets_allows_no_version():
    target_repo = FakeTargetRepository()
    version_repo = FakeTargetVersionRepository()
    service = ImportTargetsService(target_repo, version_repo)

    result = service.import_items([(Target(name="VMware Workstation"), None)])

    assert result.targets_imported == 1
    assert result.versions_imported == 0
    assert version_repo.versions == []
```

- [ ] **Step 2: Write failing sync service tests**

Create `tests/application/test_sync_vulnerabilities.py`:

```python
from updater.application.sync_vulnerabilities import SyncVulnerabilitiesService
from updater.domain.models import Target, TargetVulnerability, Vulnerability


class FakeTargetRepository:
    def __init__(self, targets):
        self.targets = targets

    def list_all(self):
        return self.targets

    def find_by_name(self, name: str):
        return next((target for target in self.targets if target.name == name), None)

    def upsert(self, target):
        return target


class FakeVulnerabilityRepository:
    def __init__(self):
        self.items = {}

    def upsert(self, vulnerability: Vulnerability) -> Vulnerability:
        vulnerability.id = vulnerability.id or vulnerability.advisory_id
        self.items[vulnerability.advisory_id] = vulnerability
        return vulnerability

    def list_all(self):
        return list(self.items.values())


class FakeTargetVulnerabilityRepository:
    def __init__(self):
        self.links = []

    def upsert(self, link: TargetVulnerability) -> TargetVulnerability:
        link.id = link.id or f"link-{len(self.links) + 1}"
        self.links.append(link)
        return link

    def list_all(self):
        return self.links


class FakeSource:
    source_name = "fake"

    def search(self, target: Target, query: str):
        if query == "Adobe Reader":
            return [(
                Vulnerability(advisory_id="CVE-2025-1234", sources=["fake"], description="Example"),
                {"matched": query},
            )]
        return []


def test_sync_searches_name_and_aliases_and_links_evidence():
    target = Target(id="target-1", name="Adobe Acrobat Reader", aliases=["Adobe Reader"])
    vuln_repo = FakeVulnerabilityRepository()
    link_repo = FakeTargetVulnerabilityRepository()
    service = SyncVulnerabilitiesService(
        target_repo=FakeTargetRepository([target]),
        vulnerability_repo=vuln_repo,
        target_vulnerability_repo=link_repo,
        sources=[FakeSource()],
    )

    result = service.sync_all()

    assert result.targets_processed == 1
    assert result.vulnerabilities_seen == 1
    assert vuln_repo.list_all()[0].advisory_id == "CVE-2025-1234"
    assert link_repo.links[0].target_id == "target-1"
    assert link_repo.links[0].matched_queries == ["Adobe Reader"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/application/test_import_targets.py tests/application/test_sync_vulnerabilities.py -v
```

Expected: FAIL with missing application modules.

- [ ] **Step 4: Implement application DTOs and services**

Create `src/updater/application/dto.py`:

```python
from dataclasses import dataclass, field


@dataclass
class ImportTargetsResult:
    targets_imported: int = 0
    versions_imported: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class SyncResult:
    targets_processed: int = 0
    vulnerabilities_seen: int = 0
    links_updated: int = 0
    errors: list[str] = field(default_factory=list)
```

Create `src/updater/application/import_targets.py`:

```python
from __future__ import annotations

from updater.application.dto import ImportTargetsResult
from updater.domain.models import Target, TargetVersion
from updater.domain.repositories import TargetRepository, TargetVersionRepository


class ImportTargetsService:
    def __init__(self, target_repo: TargetRepository, version_repo: TargetVersionRepository):
        self.target_repo = target_repo
        self.version_repo = version_repo

    def import_items(self, items: list[tuple[Target, TargetVersion | None]]) -> ImportTargetsResult:
        result = ImportTargetsResult()
        for target, version in items:
            saved_target = self.target_repo.upsert(target)
            result.targets_imported += 1
            if version is not None:
                version.target_id = saved_target.id
                self.version_repo.upsert(version)
                result.versions_imported += 1
        return result
```

Create `src/updater/application/sync_vulnerabilities.py`:

```python
from __future__ import annotations

from updater.application.dto import SyncResult
from updater.domain.models import Target, TargetVulnerability
from updater.domain.repositories import (
    TargetRepository,
    TargetVulnerabilityRepository,
    VulnerabilityRepository,
    VulnerabilitySource,
)


class SyncVulnerabilitiesService:
    def __init__(
        self,
        *,
        target_repo: TargetRepository,
        vulnerability_repo: VulnerabilityRepository,
        target_vulnerability_repo: TargetVulnerabilityRepository,
        sources: list[VulnerabilitySource],
    ):
        self.target_repo = target_repo
        self.vulnerability_repo = vulnerability_repo
        self.target_vulnerability_repo = target_vulnerability_repo
        self.sources = sources

    def sync_all(self) -> SyncResult:
        return self._sync_targets(self.target_repo.list_all())

    def sync_one(self, target_name: str) -> SyncResult:
        target = self.target_repo.find_by_name(target_name)
        return self._sync_targets([] if target is None else [target])

    def _sync_targets(self, targets: list[Target]) -> SyncResult:
        result = SyncResult(targets_processed=len(targets))
        for target in targets:
            for query in target.search_queries():
                for source in self.sources:
                    try:
                        matches = source.search(target, query)
                    except Exception as exc:
                        result.errors.append(f"{source.source_name}:{target.name}:{query}:{exc}")
                        continue
                    for vulnerability, evidence in matches:
                        saved_vulnerability = self.vulnerability_repo.upsert(vulnerability)
                        link = TargetVulnerability(
                            target_id=target.id or target.normalized_name,
                            vulnerability_id=saved_vulnerability.id or saved_vulnerability.advisory_id,
                        )
                        link.add_evidence(
                            source=source.source_name,
                            matched_query=query,
                            evidence=evidence,
                        )
                        self.target_vulnerability_repo.upsert(link)
                        result.vulnerabilities_seen += 1
                        result.links_updated += 1
        return result
```

- [ ] **Step 5: Run application tests**

Run:

```bash
python -m pytest tests/application/test_import_targets.py tests/application/test_sync_vulnerabilities.py -v
```

Expected: PASS.

- [ ] **Step 6: Checkpoint**

Run:

```bash
python -m pytest tests/domain tests/infrastructure/test_csv_loader.py tests/application -v
```

Expected: PASS. If git exists, commit:

```bash
git add src/updater/application tests/application
git commit -m "feat: add target import and vulnerability sync services"
```

---

### Task 5: NVD source adapter and normalizer

**Files:**
- Create: `src/updater/infrastructure/sources/nvd.py`
- Create: `tests/infrastructure/sources/test_nvd.py`

- [ ] **Step 1: Write failing NVD normalizer tests**

Create `tests/infrastructure/sources/test_nvd.py`:

```python
from updater.domain.models import Target
from updater.infrastructure.sources.nvd import NvdSource, normalize_nvd_item


def test_normalize_nvd_item_extracts_required_fields():
    raw = {
        "cve": {
            "id": "CVE-2025-1234",
            "published": "2025-01-02T03:04:05.000",
            "descriptions": [{"lang": "en", "value": "Example vulnerability"}],
            "references": {"referenceData": [{"url": "https://example.test/ref"}]},
            "metrics": {
                "cvssMetricV31": [{"cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL"}}]
            },
        }
    }

    vulnerability = normalize_nvd_item(raw)

    assert vulnerability.advisory_id == "CVE-2025-1234"
    assert vulnerability.cvss_score == 9.8
    assert vulnerability.severity == "critical"
    assert vulnerability.description == "Example vulnerability"
    assert vulnerability.references == ["https://example.test/ref"]
    assert vulnerability.sources == ["nvd"]


def test_nvd_source_builds_query_request(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"vulnerabilities": []}

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return FakeResponse()

    source = NvdSource(get=fake_get)

    result = source.search(Target(name="Adobe Acrobat Reader"), "Adobe Reader")

    assert result == []
    assert calls[0][0] == "https://services.nvd.nist.gov/rest/json/cves/2.0"
    assert calls[0][1]["keywordSearch"] == "Adobe Reader"
    assert calls[0][2] == 30
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/infrastructure/sources/test_nvd.py -v
```

Expected: FAIL with missing `NvdSource`.

- [ ] **Step 3: Implement NVD adapter**

Create `src/updater/infrastructure/sources/nvd.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import requests

from updater.domain.models import Target, Vulnerability

NVD_CVES_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"


class NvdSource:
    source_name = "nvd"

    def __init__(self, get: Callable[..., Any] | None = None, api_key: str | None = None):
        self.get = get or requests.get
        self.api_key = api_key

    def search(self, target: Target, query: str) -> list[tuple[Vulnerability, dict]]:
        params = {"keywordSearch": query}
        if self.api_key:
            params["apiKey"] = self.api_key
        response = self.get(NVD_CVES_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        results: list[tuple[Vulnerability, dict]] = []
        for item in payload.get("vulnerabilities", []):
            vulnerability = normalize_nvd_item(item)
            results.append((vulnerability, {"query": query, "nvd": item}))
        return results


def normalize_nvd_item(item: dict[str, Any]) -> Vulnerability:
    cve = item["cve"]
    metrics = cve.get("metrics", {})
    cvss_score, severity = _extract_cvss(metrics)
    references = [ref["url"] for ref in cve.get("references", {}).get("referenceData", []) if ref.get("url")]
    return Vulnerability.from_source(
        source="nvd",
        advisory_id=cve["id"],
        cve_id=cve["id"],
        cvss_score=cvss_score,
        severity=severity,
        description=_english_description(cve.get("descriptions", [])),
        references=references,
        published_date=_parse_nvd_datetime(cve.get("published")),
        raw=item,
    )


def _english_description(descriptions: list[dict[str, str]]) -> str | None:
    for description in descriptions:
        if description.get("lang") == "en":
            return description.get("value")
    return descriptions[0].get("value") if descriptions else None


def _extract_cvss(metrics: dict[str, Any]) -> tuple[float | None, str | None]:
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        values = metrics.get(key) or []
        if values:
            cvss_data = values[0].get("cvssData", {})
            score = cvss_data.get("baseScore")
            severity = cvss_data.get("baseSeverity") or values[0].get("baseSeverity")
            return score, severity.lower() if isinstance(severity, str) else None
    return None, None


def _parse_nvd_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    if normalized.endswith(".000"):
        normalized = normalized[:-4]
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
```

- [ ] **Step 4: Run NVD tests**

Run:

```bash
python -m pytest tests/infrastructure/sources/test_nvd.py -v
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run:

```bash
python -m pytest tests/infrastructure/sources/test_nvd.py tests/domain/test_models.py -v
```

Expected: PASS. If git exists, commit:

```bash
git add src/updater/infrastructure/sources/nvd.py tests/infrastructure/sources/test_nvd.py
git commit -m "feat: add nvd vulnerability source"
```

---

### Task 6: ZDI source adapter and normalizer

**Files:**
- Create: `src/updater/infrastructure/sources/zdi.py`
- Create: `tests/infrastructure/sources/test_zdi.py`

- [ ] **Step 1: Write failing ZDI normalizer tests**

Create `tests/infrastructure/sources/test_zdi.py`:

```python
from updater.domain.models import Target
from updater.infrastructure.sources.zdi import ZdiSource, normalize_zdi_advisory, parse_zdi_search_results


def test_normalize_zdi_advisory_prefers_cve_id():
    raw = {
        "zdi_id": "ZDI-CAN-12345",
        "cve_id": "CVE-2025-1234",
        "cvss_score": 8.8,
        "severity": "High",
        "description": "Example ZDI advisory",
        "references": ["https://example.test/zdi"],
        "published_date": "2025-02-03",
    }

    vulnerability = normalize_zdi_advisory(raw)

    assert vulnerability.advisory_id == "CVE-2025-1234"
    assert vulnerability.aliases == ["ZDI-CAN-12345"]
    assert vulnerability.severity == "high"
    assert vulnerability.sources == ["zdi"]


def test_normalize_zdi_advisory_uses_zdi_id_without_cve():
    raw = {
        "zdi_id": "ZDI-CAN-99999",
        "cve_id": None,
        "cvss_score": None,
        "severity": None,
        "description": "No CVE assigned",
        "references": [],
        "published_date": None,
    }

    vulnerability = normalize_zdi_advisory(raw)

    assert vulnerability.advisory_id == "ZDI-CAN-99999"
    assert vulnerability.aliases == []


def test_parse_zdi_search_results_extracts_detail_links():
    html = '''
    <html><body>
      <a href="/advisories/ZDI-25-001/">ZDI-25-001</a>
      <a href="/advisories/ZDI-CAN-12345/">ZDI-CAN-12345</a>
    </body></html>
    '''

    assert parse_zdi_search_results(html) == [
        "https://www.zerodayinitiative.com/advisories/ZDI-25-001/",
        "https://www.zerodayinitiative.com/advisories/ZDI-CAN-12345/",
    ]


def test_zdi_source_returns_empty_when_search_has_no_links():
    class FakeResponse:
        text = "<html><body>No advisories</body></html>"

        def raise_for_status(self):
            return None

    def fake_get(url, params=None, timeout=30):
        return FakeResponse()

    source = ZdiSource(get=fake_get)

    assert source.search(Target(name="Adobe Reader"), "Adobe Reader") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/infrastructure/sources/test_zdi.py -v
```

Expected: FAIL with missing `ZdiSource`.

- [ ] **Step 3: Implement ZDI adapter**

Create `src/updater/infrastructure/sources/zdi.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
import re

from bs4 import BeautifulSoup
import requests

from updater.domain.models import Target, Vulnerability

ZDI_BASE_URL = "https://www.zerodayinitiative.com"
ZDI_ADVISORIES_URL = f"{ZDI_BASE_URL}/advisories/"


class ZdiSource:
    source_name = "zdi"

    def __init__(self, get: Callable[..., Any] | None = None):
        self.get = get or requests.get

    def search(self, target: Target, query: str) -> list[tuple[Vulnerability, dict]]:
        response = self.get(ZDI_ADVISORIES_URL, params={"q": query}, timeout=30)
        response.raise_for_status()
        detail_urls = parse_zdi_search_results(response.text)
        results: list[tuple[Vulnerability, dict]] = []
        for detail_url in detail_urls:
            detail_response = self.get(detail_url, timeout=30)
            detail_response.raise_for_status()
            raw = parse_zdi_detail(detail_response.text, detail_url)
            vulnerability = normalize_zdi_advisory(raw)
            results.append((vulnerability, {"query": query, "zdi": raw}))
        return results


def parse_zdi_search_results(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "/advisories/" not in href:
            continue
        if not re.search(r"ZDI-(?:CAN-)?\d", href):
            continue
        url = href if href.startswith("http") else f"{ZDI_BASE_URL}{href}"
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def parse_zdi_detail(html: str, detail_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    zdi_id = _first_match(r"\bZDI-(?:CAN-)?\d{2,5}-?\d*\b", text) or detail_url.rstrip("/").split("/")[-1]
    cve_id = _first_match(r"\bCVE-\d{4}-\d{4,7}\b", text)
    cvss_text = _first_match(r"CVSS[^0-9]*(\d+(?:\.\d+)?)", text)
    severity = _first_match(r"Severity\s*[:\n]\s*([A-Za-z]+)", text)
    published = _first_match(r"Published\s*[:\n]\s*(\d{4}-\d{2}-\d{2})", text)
    description = _extract_description(text)
    return {
        "zdi_id": zdi_id,
        "cve_id": cve_id,
        "cvss_score": float(cvss_text) if cvss_text else None,
        "severity": severity,
        "description": description,
        "references": [detail_url],
        "published_date": published,
        "html": html,
    }


def normalize_zdi_advisory(raw: dict[str, Any]) -> Vulnerability:
    severity = raw.get("severity")
    return Vulnerability.from_source(
        source="zdi",
        advisory_id=raw["zdi_id"],
        cve_id=raw.get("cve_id"),
        cvss_score=raw.get("cvss_score"),
        severity=severity.lower() if isinstance(severity, str) else None,
        description=raw.get("description"),
        references=raw.get("references", []),
        published_date=_parse_date(raw.get("published_date")),
        raw=raw,
    )


def _first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1) if match and match.groups() else match.group(0) if match else None


def _extract_description(text: str) -> str | None:
    match = re.search(r"Description\s*[:\n]\s*(.+?)(?:\n[A-Z][A-Za-z ]+\s*[:\n]|$)", text, flags=re.DOTALL)
    if match:
        return " ".join(match.group(1).split())
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[0] if lines else None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
```

- [ ] **Step 4: Run ZDI tests**

Run:

```bash
python -m pytest tests/infrastructure/sources/test_zdi.py -v
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run:

```bash
python -m pytest tests/infrastructure/sources -v
```

Expected: PASS. If git exists, commit:

```bash
git add src/updater/infrastructure/sources/zdi.py tests/infrastructure/sources/test_zdi.py
git commit -m "feat: add zdi vulnerability source"
```

---

### Task 7: MongoDB repositories and mapping

**Files:**
- Create: `src/updater/infrastructure/mongo.py`
- Create: `tests/infrastructure/test_mongo_mapping.py`

- [ ] **Step 1: Write failing Mongo mapping tests**

Create `tests/infrastructure/test_mongo_mapping.py`:

```python
from updater.domain.models import Target, Vulnerability
from updater.infrastructure.mongo import target_to_document, vulnerability_to_document


def test_target_document_contains_normalized_name_and_raw_metadata():
    target = Target(name=" Adobe Reader ", aliases=["Acrobat"], raw_metadata={"notes": "contest"})

    document = target_to_document(target)

    assert document["name"] == " Adobe Reader "
    assert document["normalized_name"] == "adobe reader"
    assert document["aliases"] == ["Acrobat"]
    assert document["raw_metadata"] == {"notes": "contest"}


def test_vulnerability_document_uses_advisory_id_as_unique_key():
    vulnerability = Vulnerability(advisory_id="CVE-2025-1234", sources=["nvd"], aliases=["ZDI-CAN-12345"])

    document = vulnerability_to_document(vulnerability)

    assert document["advisory_id"] == "CVE-2025-1234"
    assert document["aliases"] == ["ZDI-CAN-12345"]
    assert document["sources"] == ["nvd"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/infrastructure/test_mongo_mapping.py -v
```

Expected: FAIL with missing `updater.infrastructure.mongo`.

- [ ] **Step 3: Implement Mongo mapping and repositories**

Create `src/updater/infrastructure/mongo.py`:

```python
from __future__ import annotations

from typing import Any

from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection

from updater.domain.models import Target, TargetVersion, TargetVulnerability, Vulnerability


def target_to_document(target: Target) -> dict[str, Any]:
    return {
        "name": target.name,
        "normalized_name": target.normalized_name,
        "aliases": target.aliases,
        "vendor": target.vendor,
        "category": target.category,
        "raw_metadata": target.raw_metadata,
        "created_at": target.created_at,
        "updated_at": target.updated_at,
    }


def vulnerability_to_document(vulnerability: Vulnerability) -> dict[str, Any]:
    return {
        "advisory_id": vulnerability.advisory_id,
        "aliases": vulnerability.aliases,
        "sources": vulnerability.sources,
        "cvss_score": vulnerability.cvss_score,
        "severity": vulnerability.severity,
        "description": vulnerability.description,
        "references": vulnerability.references,
        "published_date": vulnerability.published_date,
        "raw": vulnerability.raw,
        "created_at": vulnerability.created_at,
        "updated_at": vulnerability.updated_at,
    }


class MongoDatabase:
    def __init__(self, uri: str = "mongodb://localhost:27017", database: str = "pwn2own_updater"):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[database]

    def ensure_indexes(self) -> None:
        self.db.targets.create_index([("normalized_name", ASCENDING)], unique=True)
        self.db.target_versions.create_index(
            [("target_id", ASCENDING), ("version", ASCENDING), ("version_type", ASCENDING)],
            unique=True,
            partialFilterExpression={"version": {"$type": "string"}},
        )
        self.db.vulnerabilities.create_index([("advisory_id", ASCENDING)], unique=True)
        self.db.target_vulnerabilities.create_index(
            [("target_id", ASCENDING), ("vulnerability_id", ASCENDING)],
            unique=True,
        )


class MongoTargetRepository:
    def __init__(self, collection: Collection):
        self.collection = collection

    def upsert(self, target: Target) -> Target:
        document = target_to_document(target)
        result = self.collection.find_one_and_update(
            {"normalized_name": target.normalized_name},
            {"$set": document, "$setOnInsert": {"created_at": target.created_at}},
            upsert=True,
            return_document=True,
        )
        target.id = str(result["_id"])
        return target

    def list_all(self) -> list[Target]:
        return [self._from_document(document) for document in self.collection.find().sort("name", ASCENDING)]

    def find_by_name(self, name: str) -> Target | None:
        probe = Target(name=name)
        document = self.collection.find_one({"normalized_name": probe.normalized_name})
        return self._from_document(document) if document else None

    def _from_document(self, document: dict[str, Any]) -> Target:
        return Target(
            id=str(document["_id"]),
            name=document["name"],
            aliases=document.get("aliases", []),
            vendor=document.get("vendor"),
            category=document.get("category"),
            raw_metadata=document.get("raw_metadata", {}),
            created_at=document["created_at"],
            updated_at=document["updated_at"],
        )


class MongoTargetVersionRepository:
    def __init__(self, collection: Collection):
        self.collection = collection

    def upsert(self, version: TargetVersion) -> TargetVersion:
        document = {
            "target_id": version.target_id,
            "version": version.version,
            "version_type": version.version_type,
            "release_date": version.release_date,
            "source_url": version.source_url,
            "is_latest": version.is_latest,
            "raw": version.raw,
            "first_seen_at": version.first_seen_at,
            "last_seen_at": version.last_seen_at,
        }
        result = self.collection.find_one_and_update(
            {"target_id": version.target_id, "version": version.version, "version_type": version.version_type},
            {"$set": document, "$setOnInsert": {"first_seen_at": version.first_seen_at}},
            upsert=True,
            return_document=True,
        )
        version.id = str(result["_id"])
        return version


class MongoVulnerabilityRepository:
    def __init__(self, collection: Collection):
        self.collection = collection

    def upsert(self, vulnerability: Vulnerability) -> Vulnerability:
        document = vulnerability_to_document(vulnerability)
        result = self.collection.find_one_and_update(
            {"advisory_id": vulnerability.advisory_id},
            {
                "$set": document,
                "$addToSet": {
                    "aliases": {"$each": vulnerability.aliases},
                    "sources": {"$each": vulnerability.sources},
                    "references": {"$each": vulnerability.references},
                },
                "$setOnInsert": {"created_at": vulnerability.created_at},
            },
            upsert=True,
            return_document=True,
        )
        vulnerability.id = str(result["_id"])
        return vulnerability

    def list_all(self) -> list[Vulnerability]:
        return [
            Vulnerability(
                id=str(document["_id"]),
                advisory_id=document["advisory_id"],
                aliases=document.get("aliases", []),
                sources=document.get("sources", []),
                cvss_score=document.get("cvss_score"),
                severity=document.get("severity"),
                description=document.get("description"),
                references=document.get("references", []),
                published_date=document.get("published_date"),
                raw=document.get("raw", {}),
                created_at=document["created_at"],
                updated_at=document["updated_at"],
            )
            for document in self.collection.find().sort("advisory_id", ASCENDING)
        ]


class MongoTargetVulnerabilityRepository:
    def __init__(self, collection: Collection):
        self.collection = collection

    def upsert(self, link: TargetVulnerability) -> TargetVulnerability:
        document = {
            "target_id": link.target_id,
            "vulnerability_id": link.vulnerability_id,
            "affected_versions": link.affected_versions,
            "fixed_versions": link.fixed_versions,
            "matched_queries": link.matched_queries,
            "evidence_sources": link.evidence_sources,
            "last_seen_at": link.last_seen_at,
        }
        result = self.collection.find_one_and_update(
            {"target_id": link.target_id, "vulnerability_id": link.vulnerability_id},
            {
                "$set": document,
                "$addToSet": {
                    "matched_queries": {"$each": link.matched_queries},
                    "evidence_sources": {"$each": link.evidence_sources},
                },
                "$setOnInsert": {"first_seen_at": link.first_seen_at},
            },
            upsert=True,
            return_document=True,
        )
        link.id = str(result["_id"])
        return link

    def list_all(self) -> list[TargetVulnerability]:
        return [
            TargetVulnerability(
                id=str(document["_id"]),
                target_id=document["target_id"],
                vulnerability_id=document["vulnerability_id"],
                affected_versions=document.get("affected_versions", []),
                fixed_versions=document.get("fixed_versions", []),
                matched_queries=document.get("matched_queries", []),
                evidence_sources=document.get("evidence_sources", []),
                first_seen_at=document["first_seen_at"],
                last_seen_at=document["last_seen_at"],
            )
            for document in self.collection.find()
        ]
```

- [ ] **Step 4: Run Mongo mapping tests**

Run:

```bash
python -m pytest tests/infrastructure/test_mongo_mapping.py -v
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run:

```bash
python -m pytest tests/infrastructure/test_mongo_mapping.py tests/domain/test_models.py -v
```

Expected: PASS. If git exists, commit:

```bash
git add src/updater/infrastructure/mongo.py tests/infrastructure/test_mongo_mapping.py
git commit -m "feat: add mongodb repositories"
```

---

### Task 8: JSON export service and exporter

**Files:**
- Create: `src/updater/application/export_json.py`
- Create: `src/updater/infrastructure/json_exporter.py`
- Create: `tests/application/test_export_json.py`
- Create: `tests/infrastructure/test_json_exporter.py`

- [ ] **Step 1: Write failing export tests**

Create `tests/application/test_export_json.py`:

```python
from updater.application.export_json import ExportService
from updater.domain.models import Target, TargetVulnerability, Vulnerability


class FakeTargetRepository:
    def list_all(self):
        return [Target(id="target-1", name="Adobe Reader", aliases=["Acrobat"])]


class FakeVulnerabilityRepository:
    def list_all(self):
        return [Vulnerability(id="vuln-1", advisory_id="CVE-2025-1234", sources=["nvd"])]


class FakeTargetVulnerabilityRepository:
    def list_all(self):
        return [TargetVulnerability(target_id="target-1", vulnerability_id="vuln-1", matched_queries=["Adobe Reader"])]


def test_export_service_returns_json_compatible_snapshot():
    service = ExportService(FakeTargetRepository(), FakeVulnerabilityRepository(), FakeTargetVulnerabilityRepository())

    snapshot = service.snapshot()

    assert snapshot["targets"][0]["name"] == "Adobe Reader"
    assert snapshot["vulnerabilities"][0]["advisory_id"] == "CVE-2025-1234"
    assert snapshot["target_vulnerabilities"][0]["target_id"] == "target-1"
```

Create `tests/infrastructure/test_json_exporter.py`:

```python
import json
from pathlib import Path

from updater.infrastructure.json_exporter import JsonExporter


def test_json_exporter_writes_pretty_json(tmp_path: Path):
    output = tmp_path / "output.json"

    JsonExporter().write(output, {"targets": [{"name": "Adobe Reader"}]})

    assert json.loads(output.read_text(encoding="utf-8")) == {"targets": [{"name": "Adobe Reader"}]}
    assert output.read_text(encoding="utf-8").startswith("{\n  ")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/application/test_export_json.py tests/infrastructure/test_json_exporter.py -v
```

Expected: FAIL with missing export modules.

- [ ] **Step 3: Implement export service and JSON writer**

Create `src/updater/application/export_json.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from updater.domain.repositories import TargetRepository, TargetVulnerabilityRepository, VulnerabilityRepository


class ExportService:
    def __init__(
        self,
        target_repo: TargetRepository,
        vulnerability_repo: VulnerabilityRepository,
        target_vulnerability_repo: TargetVulnerabilityRepository,
    ):
        self.target_repo = target_repo
        self.vulnerability_repo = vulnerability_repo
        self.target_vulnerability_repo = target_vulnerability_repo

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "targets": [self._serialize(item) for item in self.target_repo.list_all()],
            "vulnerabilities": [self._serialize(item) for item in self.vulnerability_repo.list_all()],
            "target_vulnerabilities": [self._serialize(item) for item in self.target_vulnerability_repo.list_all()],
        }

    def _serialize(self, item: object) -> dict[str, Any]:
        data = dict(item.__dict__)
        for key, value in list(data.items()):
            if isinstance(value, datetime):
                data[key] = value.isoformat()
        return data
```

Create `src/updater/infrastructure/json_exporter.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any
import json


class JsonExporter:
    def write(self, path: str | Path, data: dict[str, Any]) -> None:
        Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
```

- [ ] **Step 4: Run export tests**

Run:

```bash
python -m pytest tests/application/test_export_json.py tests/infrastructure/test_json_exporter.py -v
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run:

```bash
python -m pytest tests/application/test_export_json.py tests/infrastructure/test_json_exporter.py -v
```

Expected: PASS. If git exists, commit:

```bash
git add src/updater/application/export_json.py src/updater/infrastructure/json_exporter.py tests/application/test_export_json.py tests/infrastructure/test_json_exporter.py
git commit -m "feat: add json export service"
```

---

### Task 9: CLI wiring

**Files:**
- Create: `src/updater/presentation/cli.py`
- Create: `tests/presentation/test_cli.py`
- Create: `samples/targets.csv`
- Create: `README.md`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/presentation/test_cli.py`:

```python
from updater.presentation.cli import build_parser


def test_parser_accepts_sync_targets():
    args = build_parser().parse_args(["sync", "--targets", "targets.csv"])

    assert args.command == "sync"
    assert args.targets == "targets.csv"


def test_parser_accepts_sync_cves_target_filter():
    args = build_parser().parse_args(["sync-cves", "--target", "Adobe Reader"])

    assert args.command == "sync-cves"
    assert args.target == "Adobe Reader"


def test_parser_accepts_export_json_output():
    args = build_parser().parse_args(["export-json", "--out", "output.json"])

    assert args.command == "export-json"
    assert args.out == "output.json"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/presentation/test_cli.py -v
```

Expected: FAIL with missing CLI module.

- [ ] **Step 3: Implement CLI parser and command wiring**

Create `src/updater/presentation/cli.py`:

```python
from __future__ import annotations

from argparse import ArgumentParser, Namespace
import os

from updater.application.export_json import ExportService
from updater.application.import_targets import ImportTargetsService
from updater.application.sync_vulnerabilities import SyncVulnerabilitiesService
from updater.infrastructure.csv_loader import CsvTargetLoader
from updater.infrastructure.json_exporter import JsonExporter
from updater.infrastructure.mongo import (
    MongoDatabase,
    MongoTargetRepository,
    MongoTargetVersionRepository,
    MongoTargetVulnerabilityRepository,
    MongoVulnerabilityRepository,
)
from updater.infrastructure.sources.nvd import NvdSource
from updater.infrastructure.sources.zdi import ZdiSource


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="updater")
    parser.add_argument("--mongo-uri", default=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
    parser.add_argument("--mongo-db", default=os.environ.get("MONGODB_DATABASE", "pwn2own_updater"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser("sync")
    sync.add_argument("--targets", required=True)

    import_targets = subparsers.add_parser("import-targets")
    import_targets.add_argument("--targets", required=True)

    sync_cves = subparsers.add_parser("sync-cves")
    sync_cves.add_argument("--target")

    subparsers.add_parser("list-targets")

    export_json = subparsers.add_parser("export-json")
    export_json.add_argument("--out", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_command(args)


def run_command(args: Namespace) -> int:
    database = MongoDatabase(args.mongo_uri, args.mongo_db)
    database.ensure_indexes()
    target_repo = MongoTargetRepository(database.db.targets)
    version_repo = MongoTargetVersionRepository(database.db.target_versions)
    vulnerability_repo = MongoVulnerabilityRepository(database.db.vulnerabilities)
    link_repo = MongoTargetVulnerabilityRepository(database.db.target_vulnerabilities)

    if args.command == "import-targets":
        load_result = CsvTargetLoader().load(args.targets)
        service = ImportTargetsService(target_repo, version_repo)
        result = service.import_items([(item.target, item.version) for item in load_result.items])
        print(f"targets_imported={result.targets_imported} versions_imported={result.versions_imported} errors={len(load_result.errors)}")
        for error in load_result.errors:
            print(error)
        return 0 if not load_result.errors else 1

    if args.command == "sync":
        load_result = CsvTargetLoader().load(args.targets)
        import_result = ImportTargetsService(target_repo, version_repo).import_items(
            [(item.target, item.version) for item in load_result.items]
        )
        sync_result = SyncVulnerabilitiesService(
            target_repo=target_repo,
            vulnerability_repo=vulnerability_repo,
            target_vulnerability_repo=link_repo,
            sources=[NvdSource(), ZdiSource()],
        ).sync_all()
        print(
            " ".join([
                f"targets_imported={import_result.targets_imported}",
                f"versions_imported={import_result.versions_imported}",
                f"targets_processed={sync_result.targets_processed}",
                f"vulnerabilities_seen={sync_result.vulnerabilities_seen}",
                f"links_updated={sync_result.links_updated}",
                f"errors={len(load_result.errors) + len(sync_result.errors)}",
            ])
        )
        for error in [*load_result.errors, *sync_result.errors]:
            print(error)
        return 0 if not load_result.errors and not sync_result.errors else 1

    if args.command == "sync-cves":
        service = SyncVulnerabilitiesService(
            target_repo=target_repo,
            vulnerability_repo=vulnerability_repo,
            target_vulnerability_repo=link_repo,
            sources=[NvdSource(), ZdiSource()],
        )
        result = service.sync_one(args.target) if args.target else service.sync_all()
        print(f"targets_processed={result.targets_processed} vulnerabilities_seen={result.vulnerabilities_seen} links_updated={result.links_updated} errors={len(result.errors)}")
        for error in result.errors:
            print(error)
        return 0 if not result.errors else 1

    if args.command == "list-targets":
        for target in target_repo.list_all():
            print(target.name)
        return 0

    if args.command == "export-json":
        snapshot = ExportService(target_repo, vulnerability_repo, link_repo).snapshot()
        JsonExporter().write(args.out, snapshot)
        print(f"exported={args.out}")
        return 0

    parser_error = f"unsupported command: {args.command}"
    print(parser_error)
    return 2
```

Create `samples/targets.csv`:

```csv
name,aliases,vendor,category,version,version_type
Adobe Acrobat Reader,Acrobat Reader;Adobe Reader,Adobe,document reader,,
VMware Workstation,VMware Workstation Pro;Workstation,VMware,virtualization,,
```

Create `README.md`:

```markdown
# Pwn2Own Target Updater

Python CLI prototype for importing Pwn2Own targets and syncing vulnerability data from NIST NVD and ZDI into MongoDB.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```

MongoDB defaults:

```text
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=pwn2own_updater
```

## Commands

```bash
updater import-targets --targets samples/targets.csv
updater sync --targets samples/targets.csv
updater sync-cves
updater sync-cves --target "Adobe Acrobat Reader"
updater list-targets
updater export-json --out output.json
```
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
python -m pytest tests/presentation/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run:

```bash
python -m pytest tests/presentation/test_cli.py -v
```

Expected: PASS. If git exists, commit:

```bash
git add src/updater/presentation/cli.py tests/presentation/test_cli.py samples/targets.csv README.md
git commit -m "feat: add updater cli"
```

---

### Task 10: Full verification and MongoDB smoke test

**Files:**
- Modify only if tests reveal concrete defects in files created by earlier tasks.

- [ ] **Step 1: Install dependencies in a virtual environment**

Run:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```

Expected: packages install successfully and `updater` console script is available.

- [ ] **Step 2: Run the full unit test suite**

Run:

```bash
. .venv/bin/activate
python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 3: Verify MongoDB connectivity**

Run:

```bash
. .venv/bin/activate
python - <<'PY'
from updater.infrastructure.mongo import MongoDatabase

db = MongoDatabase()
db.client.admin.command('ping')
db.ensure_indexes()
print('mongodb_ok')
PY
```

Expected: prints `mongodb_ok`. If this fails with connection refused, start local MongoDB and rerun the same command.

- [ ] **Step 4: Smoke test target import**

Run:

```bash
. .venv/bin/activate
updater import-targets --targets samples/targets.csv
```

Expected: prints a summary like `targets_imported=2 versions_imported=0 errors=0`.

- [ ] **Step 5: Smoke test listing targets**

Run:

```bash
. .venv/bin/activate
updater list-targets
```

Expected: output includes:

```text
Adobe Acrobat Reader
VMware Workstation
```

- [ ] **Step 6: Smoke test JSON export**

Run:

```bash
. .venv/bin/activate
updater export-json --out output.json
python -m json.tool output.json >/dev/null
```

Expected: both commands exit with status 0 and `output.json` exists.

- [ ] **Step 7: Smoke test vulnerability sync with one target**

Run:

```bash
. .venv/bin/activate
updater sync-cves --target "Adobe Acrobat Reader"
```

Expected: command exits with status 0 if NVD and ZDI are reachable. The printed summary includes `targets_processed=1`. If ZDI changes its HTML structure, the command may report a ZDI source error while NVD still works; fix the parser only after capturing the failing HTML shape in a unit test.

- [ ] **Step 8: Final checkpoint**

Run:

```bash
. .venv/bin/activate
python -m pytest -v
```

Expected: all tests PASS. If git exists, commit final fixes:

```bash
git add pyproject.toml requirements.txt requirements-dev.txt README.md samples src tests
git commit -m "test: verify updater prototype"
```

---

## Self-Review

Spec coverage:

- CLI prototype: Task 9 and Task 10.
- Core reusable for future Discord bot: Tasks 2, 4, 8, and 9 keep business logic outside CLI.
- OOP target objects from raw CSV data: Tasks 2 and 3.
- Flexible CSV with optional version fields: Task 3.
- MongoDB storage and unique indexes: Task 7.
- NVD vulnerability collection: Task 5.
- ZDI vulnerability collection and CVE preference: Task 6.
- Duplicate prevention via upsert: Tasks 4 and 7.
- JSON export: Task 8 and Task 9.
- Testing strategy: Tasks 1 through 10 include focused tests and final smoke checks.

Placeholder scan: no incomplete sections are intentionally left for the implementer. Each code-writing step includes concrete file contents.

Type consistency: names used across tasks are consistent: `Target`, `TargetVersion`, `Vulnerability`, `TargetVulnerability`, repository protocols, `ImportTargetsService`, `SyncVulnerabilitiesService`, `ExportService`, `CsvTargetLoader`, `NvdSource`, `ZdiSource`, and Mongo repository classes.
