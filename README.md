# Pwn2Own Target Updater

Pwn2Own Target Updater is a Discord bot for tracking vulnerability information for Pwn2Own targets.

It imports target/product data from a flexible CSV file, stores normalized data in MongoDB, and syncs vulnerability information from:

- NIST NVD CVE API
- ZDI advisory pages

The bot runs as a long-lived Discord process and exposes slash commands for administration and querying.

## Features

- Import targets from CSV via Discord
- Support target aliases for better CVE/ZDI search coverage
- Optionally store software or firmware version metadata
- Sync vulnerability data from NVD and ZDI
- Prefer CVE IDs when a ZDI advisory includes a CVE
- Store data in MongoDB with upsert behavior to avoid duplicates
- Scheduled automatic CVE/ZDI sync and notification
- Export stored data to JSON

## Requirements

- Python 3.10+
- MongoDB running locally or remotely
- Internet access for NVD/ZDI sync
- A Discord bot application with the **Server Members Intent** enabled

## Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
. .venv/bin/activate
```

Install the package with development dependencies:

```bash
pip install -e ".[dev]"
```

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

The bot requires `.env` to exist with valid values for:

- `DISCORD_TOKEN` — bot token from the Discord Developer Portal
- `DISCORD_GUILD_ID` — server ID where the bot operates
- `DISCORD_CHANNEL_ID` — channel ID for scheduled notifications
- `DISCORD_ADMIN_ROLE_ID` — role ID that can run admin-only commands
- `SYNC_TIME` — daily CVE sync time in `HH:MM` using `TIMEZONE`
- `NOTIFY_TIME` — daily notification time in `HH:MM` using `TIMEZONE`
- `TIMEZONE` — timezone for scheduled times and "today" filters; defaults to `UTC+7`
- `MONGODB_URI` — MongoDB connection string
- `MONGODB_DATABASE` — MongoDB database name

### Server Members Intent

The bot sets `intents.members = True`, so you must enable the privileged **Server Members Intent** for the bot application in the Discord Developer Portal under **Bot > Privileged Gateway Intents**.

## Running the bot

```bash
updater-bot
```

The bot connects to Discord, registers slash commands, and starts the scheduler.

## Slash commands

| Command | Permission | Description |
| --- | --- | --- |
| `/import-targets` | Admin | Import targets from a CSV attachment |
| `/add-target` | Admin | Add a single target |
| `/remove-target` | Admin | Remove a target |
| `/clear-database confirm: DELETE` | Admin | Clear all targets, versions, vulnerabilities, and links |
| `/show-target <name>` | Open | Show details for a named target |
| `/list-targets` | Open | List all imported targets |
| `/search-vulns [year] [from_date] [to_date]` | Open | Search stored vulnerabilities by advisory/published year and collection date range. If no dates are supplied, defaults to vulnerabilities stored today. Dates use `YYYY-MM-DD`. |
| `/add-vuln` | Admin | Manually add a vulnerability |
| `/sync-cves [target]` | Admin | Sync CVE/ZDI data and return an ephemeral result |
| `/set-schedule <sync_time> <notify_time>` | Admin | Change the daily sync and notification times |
| `/show-schedule` | Open | Show the current schedule |

Read-only commands (`/show-target`, `/list-targets`, `/search-vulns`, and `/show-schedule`) are open to all server members. All other commands require the admin role configured with `DISCORD_ADMIN_ROLE_ID`.

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

## Data model overview

The bot stores four main MongoDB collections:

- `targets` — canonical target/product/model identities
- `target_versions` — optional software or firmware versions for each target
- `vulnerabilities` — normalized CVE/ZDI vulnerability records
- `target_vulnerabilities` — links between targets and vulnerabilities, including matched aliases and source evidence

Duplicate prevention is handled with MongoDB indexes and upsert operations.

## Testing

Run the full test suite:

```bash
pytest -q
```

## Notes

- MongoDB must be running before starting the bot.
- NVD/ZDI sync commands require network access.
- ZDI does not provide the same stable API shape as NVD, so its scraper may need updates if the website layout changes.
