# Pwn2Own Target Updater Design

## Goal

Build a Python CLI prototype for collecting vulnerability information about Pwn2Own targets. The prototype should keep the core application independent from the CLI so the same core can later be reused by a Discord bot.

The first implemented module will collect CVE/ZDI vulnerability data for each target using NIST NVD and ZDI. MongoDB is the primary storage backend.

## Architecture

Use a lightweight Clean Architecture layout:

```text
CLI / future Discord Bot
        |
        v
Application Services
  - ImportTargetsService
  - SyncVulnerabilitiesService
  - ExportService
        |
        v
Domain
  - Target
  - TargetVersion
  - Vulnerability
  - TargetVulnerability
        |
        +-------------------+
        |                   |
        v                   v
Source Adapters        Repository Interfaces
  - NVD API              - TargetRepository
  - ZDI scraper          - TargetVersionRepository
                         - VulnerabilityRepository
                         - TargetVulnerabilityRepository
                              |
                              v
                         MongoDB implementation
```

### Layers

- `domain`: pure Python objects and domain rules. It does not depend on CLI, MongoDB, HTTP, NVD, or ZDI.
- `application`: use cases that coordinate loaders, sources, and repositories.
- `infrastructure`: MongoDB repositories, CSV loader, NVD client, ZDI scraper, JSON exporter.
- `presentation`: CLI prototype. It parses arguments, calls application services, and prints results.

The future Discord bot should be another presentation adapter that calls the same application services.

## Domain model

### Target

Represents a Pwn2Own product/model identity.

Fields:

- `id`
- `name`: canonical target/product/model name
- `aliases`: alternative names used for searching
- `vendor`: optional
- `category`: optional
- `raw_metadata`: optional user-provided fields from CSV that are not first-class fields
- `created_at`
- `updated_at`

### TargetVersion

Represents a software or firmware version for a target. This prepares the system for future release tracking.

Fields:

- `id`
- `target_id`
- `version`: software or firmware version, nullable when not provided by input
- `version_type`: `software`, `firmware`, `hardware`, or `unknown`, nullable when not provided
- `release_date`: optional
- `source_url`: optional
- `is_latest`: optional boolean
- `raw`: source-specific raw data
- `first_seen_at`
- `last_seen_at`

### Vulnerability

Represents a normalized vulnerability/advisory.

Fields:

- `id`
- `advisory_id`: canonical ID. Prefer CVE ID when one exists; otherwise use ZDI advisory/candidate ID.
- `aliases`: additional IDs such as ZDI advisory ID, ZDI-CAN ID, vendor advisory IDs
- `sources`: sources that observed this vulnerability, such as `nvd` and `zdi`
- `cvss_score`
- `severity`
- `description`
- `references`
- `published_date`
- `raw`: source-specific raw data grouped by source
- `created_at`
- `updated_at`

### TargetVulnerability

Links a target to a vulnerability and stores matching evidence.

Fields:

- `id`
- `target_id`
- `vulnerability_id`
- `affected_versions`: optional list if source data provides it
- `fixed_versions`: optional list if source data provides it
- `matched_queries`: target name/alias values that matched
- `evidence_sources`: source-specific evidence from NVD/ZDI
- `first_seen_at`
- `last_seen_at`

## MongoDB collections and indexes

Collections:

- `targets`
- `target_versions`
- `vulnerabilities`
- `target_vulnerabilities`

Indexes:

- `targets`: unique normalized `name`
- `target_versions`: unique `(target_id, version, version_type)` where version is not null
- `vulnerabilities`: unique canonical `advisory_id`
- `target_vulnerabilities`: unique `(target_id, vulnerability_id)`

All write paths should use upsert semantics so repeated syncs do not duplicate existing data.

## CSV input

CSV is a user-editable raw input format. The loader converts rows into domain objects instead of hard-coding targets in Python.

Required column:

- `name`

Optional columns:

- `aliases`: semicolon-separated aliases
- `vendor`
- `category`
- `version`
- `version_type`
- `release_date`
- `source_url`

Rules:

- Missing optional fields become `None` or empty lists.
- If `version` exists, create or update a `TargetVersion` for the row.
- If `version` is missing, create or update only the `Target` and do not require a version record.
- Unknown extra columns should be preserved in raw metadata when practical, not treated as fatal errors.

Examples:

```csv
name
Adobe Acrobat Reader
```

```csv
name,aliases,version,version_type
Adobe Acrobat Reader,Acrobat Reader;Adobe Reader,2024.005.20320,software
```

## Vulnerability source behavior

### NVD adapter

- Uses NIST NVD API.
- Searches by target `name` and each alias.
- Normalizes each result into `Vulnerability` plus target matching evidence.
- Extracts CVE ID, CVSS score, severity, description, references, and published date.

### ZDI adapter

- Uses a scraper/adapter because ZDI does not provide the same kind of public API as NVD.
- Searches by target `name` and each alias.
- Normalizes ZDI advisories into `Vulnerability` plus target matching evidence.
- If a ZDI advisory has a CVE ID, use the CVE ID as canonical `advisory_id` and store the ZDI ID in `aliases`, `references`, `raw`, and evidence.
- If a ZDI advisory has no CVE ID, use the ZDI advisory/candidate ID as canonical `advisory_id`.

## Sync data flow

For a prototype sync run:

1. CLI receives a command such as `sync --targets targets.csv`.
2. CSV loader reads raw rows.
3. Mapper converts rows into `Target` objects and optional `TargetVersion` objects.
4. Application service upserts targets and versions into MongoDB.
5. Vulnerability sync service searches NVD and ZDI using each target's canonical name and aliases.
6. Each source result is normalized.
7. Vulnerability repository upserts the canonical vulnerability.
8. Target-vulnerability repository upserts or updates the link and evidence.
9. CLI prints a short summary: targets processed, vulnerabilities created, vulnerabilities updated, links created/updated, and errors.

## CLI prototype

Use Python 3.10+ with `pip` and `venv`.

Initial commands:

- `updater sync --targets targets.csv`: import targets and sync vulnerabilities.
- `updater import-targets --targets targets.csv`: only import targets/versions.
- `updater sync-cves [--target NAME]`: sync NVD/ZDI vulnerabilities for all targets or one target.
- `updater list-targets`: show known targets.
- `updater export-json --out output.json`: export MongoDB data to JSON.

The CLI should remain a thin wrapper over application services.

## Error handling

- Invalid CSV rows without `name` should be reported and skipped.
- Missing optional fields should not fail import.
- HTTP/source failures should not corrupt existing data; report the source and target that failed.
- Re-running the same command should be idempotent.
- MongoDB connection failures should fail fast with a clear message.

## Testing strategy

- Unit test CSV parsing and mapping into domain objects.
- Unit test advisory normalization, especially ZDI advisories that include CVE IDs.
- Unit test repository upsert behavior through repository interfaces or a test MongoDB instance.
- Unit test application services with fake repositories and fake source adapters.
- Add a small integration test path for `sync` once MongoDB configuration is available.

## Out of scope for the first prototype

- Discord bot implementation.
- Automatic firmware/software release discovery.
- Full plugin registry system.
- Exploit availability tracking.
- Advanced matching/scoring beyond target name and aliases.

The design intentionally leaves extension points for these features without implementing them in the first prototype.
