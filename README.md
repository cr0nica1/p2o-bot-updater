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
