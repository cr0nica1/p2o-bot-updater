# Pwn2Own Target Updater

Pwn2Own Target Updater is a Python CLI prototype for tracking vulnerability information for Pwn2Own targets.

It imports target/product data from a flexible CSV file, stores normalized data in MongoDB, and syncs vulnerability information from:

- NIST NVD CVE API
- ZDI advisory pages

The core is separated from the CLI so the same application services can later be reused by another interface, such as a Discord bot.

## Features

- Import targets from CSV
- Support target aliases for better CVE/ZDI search coverage
- Optionally store software or firmware version metadata
- Sync vulnerability data from NVD and ZDI
- Prefer CVE IDs when a ZDI advisory includes a CVE
- Store data in MongoDB with upsert behavior to avoid duplicates
- Export stored data to JSON
- Clear all stored data or only the target list from MongoDB

## Requirements

- Python 3.10+
- MongoDB running locally or remotely
- Internet access for NVD/ZDI sync commands

## Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
. .venv/bin/activate
```

Install dependencies and the local CLI package:

```bash
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```

Verify the CLI is available:

```bash
updater --help
```

## MongoDB configuration

By default, the updater connects to:

```text
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=pwn2own_updater
```

If you use a different MongoDB URI or database name, set environment variables:

```bash
export MONGODB_URI="mongodb://localhost:27017"
export MONGODB_DATABASE="pwn2own_updater"
```

Or pass them directly to the CLI:

```bash
updater --mongo-uri "mongodb://localhost:27017" --mongo-db pwn2own_updater list-targets
```

## Target CSV format

The CSV input is intentionally flexible so users can edit it manually.

Required column:

- `name`

Optional columns:

- `aliases` — semicolon-separated alternative names
- `vendor`
- `category`
- `version`
- `version_type` — for example `software` or `firmware`
- `release_date`
- `source_url`

Unknown extra columns are preserved as raw metadata when they contain values.

Minimal example:

```csv
name
Adobe Acrobat Reader
VMware Workstation
```

Example with aliases and version metadata:

```csv
name,aliases,vendor,category,version,version_type
Adobe Acrobat Reader,Acrobat Reader;Adobe Reader,Adobe,document reader,2024.005.20320,software
VMware Workstation,VMware Workstation Pro;Workstation,VMware,virtualization,,
```

A sample file is included at:

```text
samples/targets.csv
```

## Common usage

Import targets only:

```bash
updater import-targets --targets samples/targets.csv
```

List imported targets:

```bash
updater list-targets
```

Sync CVE/ZDI data for all targets already in MongoDB:

```bash
updater sync-cves
```

Sync CVE/ZDI data for one target:

```bash
updater sync-cves --target "Adobe Acrobat Reader"
```

Import targets from CSV and immediately sync vulnerabilities:

```bash
updater sync --targets samples/targets.csv
```

Export stored data to JSON:

```bash
updater export-json --out output.json
```

Delete all stored data from every collection:

```bash
updater clear-data --yes
```

Delete only the target list:

```bash
updater clear-targets --yes
```

Both delete commands require `--yes` to prevent accidental data loss.

Validate exported JSON:

```bash
python -m json.tool output.json >/dev/null
```

## Data model overview

The updater stores four main MongoDB collections:

- `targets` — canonical target/product/model identities
- `target_versions` — optional software or firmware versions for each target
- `vulnerabilities` — normalized CVE/ZDI vulnerability records
- `target_vulnerabilities` — links between targets and vulnerabilities, including matched aliases and source evidence

Duplicate prevention is handled with MongoDB indexes and upsert operations.

## Testing

Run the full test suite:

```bash
python -m pytest -v
```

At the time of writing, the suite contains unit tests for:

- Domain models
- CSV parsing
- NVD normalization
- ZDI normalization and scraping helpers
- MongoDB document mapping
- Application services
- CLI parser
- JSON export
- Data deletion commands

## Notes

- MongoDB must be running before using commands that read or write data.
- NVD/ZDI sync commands require network access.
- ZDI does not provide the same stable API shape as NVD, so its scraper may need updates if the website layout changes.
