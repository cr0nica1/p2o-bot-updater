# Pwn2Own Target Updater

## Description

Pwn2Own Target Updater is a Discord bot and CLI toolkit for tracking vulnerability and firmware information for Pwn2Own targets.

The project stores normalized target data in MongoDB, syncs vulnerability information from public sources, and exposes Discord slash commands for target management, vulnerability lookup, scheduled notifications, and firmware lookup. It supports target aliases for broader CVE/ZDI matching and vendor firmware configuration for products whose firmware can be discovered from vendor web pages.

Main capabilities:

- Manage targets, aliases, vendors, categories, and vendor firmware aliases.
- Import targets from CSV.
- Sync vulnerabilities from NIST NVD and ZDI advisory pages.
- Search and display stored vulnerabilities in Discord.
- Schedule daily sync and notification jobs.
- Configure vendor firmware lookup URLs and regexes.
- Look up firmware versions from configured vendor pages.
- Export stored vulnerability data to JSON.

## Architecture

The codebase follows a layered architecture:

```text
src/updater/
├── domain/                  # Core models and repository protocols
├── application/             # Use cases and business logic
├── infrastructure/          # MongoDB, browser, CSV, and external source adapters
├── presentation/
│   └── discord_bot/         # Discord bot, slash commands, config, formatting
└── cli/                     # CLI entry points for firmware/vendor tools
```

### Domain layer

The domain layer defines core data models and repository interfaces:

- `Target` — product or device tracked by the bot.
- `Vulnerability` — CVE/ZDI advisory data.
- `TargetVulnerability` — link between targets and vulnerabilities.
- `VendorConfig` — firmware lookup settings for a vendor, including URL template, HTML element ID, and regex.

### Application layer

The application layer contains use cases:

- Vulnerability sync from configured sources.
- Target CSV import.
- JSON export.
- Firmware lookup using target vendor metadata and vendor firmware configuration.

### Infrastructure layer

The infrastructure layer implements external adapters:

- MongoDB repositories for targets, vulnerabilities, links, versions, and vendor configs.
- NVD and ZDI vulnerability sources.
- CSV target loader.
- Browser adapter for firmware page scraping with Playwright.

### Presentation layer

The presentation layer exposes functionality through Discord slash commands and CLI tools:

- Discord bot commands for target management, vulnerability sync/search, scheduling, vendor firmware config, and firmware lookup.
- CLI commands for vendor config management and firmware lookup.

## Installation

### Requirements

- Python 3.10+
- MongoDB running locally or remotely
- Internet access for vulnerability sync and firmware lookup
- Discord bot application with the **Server Members Intent** enabled
- Playwright Chromium installed for firmware lookup

### Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
. .venv/bin/activate
```

Install the package with development dependencies:

```bash
pip install -e ".[dev]"
```

Install Playwright browser dependencies for firmware lookup:

```bash
playwright install chromium
```

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Required environment values:

```text
DISCORD_TOKEN=...
DISCORD_GUILD_ID=...
DISCORD_CHANNEL_ID=...
DISCORD_ADMIN_ROLE_ID=...
SYNC_TIME=09:00
NOTIFY_TIME=09:15
TIMEZONE=UTC+7
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=pwn2own_updater
```

Run tests:

```bash
python -m pytest -q
```

## Usage

### Start the Discord bot

```bash
updater-bot --env .env
```

The bot syncs slash commands to the configured Discord guild on startup.

### Discord commands

Target management:

```text
/list-targets
/show-target target_id:<number>
/add-target name:<name> aliases:<semicolon-separated> vendor:<vendor> vendor_alias:<alias> category:<category>
/remove-target names:<comma-separated names>
/import-targets file:<csv attachment>
/clear-database confirm:DELETE
```

Vulnerability management:

```text
/add-vuln advisory_id:<id> description:<text> cvss_score:<score> severity:<severity> references:<urls> target_name:<target>
/sync-cves target:<optional target name>
/search-vulns severity:<optional> year:<optional> from_date:<YYYY-MM-DD> to_date:<YYYY-MM-DD>
```

Scheduling:

```text
/set-schedule sync_time:<HH:MM> notify_time:<HH:MM>
/show-schedule
```

Vendor firmware configuration and lookup:

```text
/set-vendor-firmware vendor:<vendor> url_template:<https url with {alias}> attr_id:<html element id> regex:<version/download regex>
/import-vendor-firmware file:<csv attachment>
/set-vendor-alias target_id:<number> vendor_alias:<alias>
/lookup-firmware target_id:<number> url_template:<optional> attr_id:<optional> regex:<optional>
```

Firmware lookup uses the target's `vendor` to find a saved vendor firmware config and the target's `vendor_alias` to render the vendor URL. If a target has no vendor, no vendor alias, no saved vendor config, a mismatched URL/regex, or unsupported firmware lookup, the bot returns no firmware information.

### Vendor firmware CSV format

Bulk vendor firmware import expects these columns:

```csv
vendor,url_template,attr_id,regex
Canon,https://example.com/{alias}/firmware,downloads,(v[\d.]+).*(https://[^"']+)
```

Rules:

- `url_template` must use HTTPS.
- `url_template` must contain `{alias}`.
- `attr_id` is the HTML element ID to scrape.
- `regex` must contain at least two capture groups:
  - group 1: firmware version
  - group 2: firmware download URL

### CLI tools

Manage saved vendor firmware configs:

```bash
vendor-config add \
  --vendor Canon \
  --url-template 'https://example.com/{alias}/firmware' \
  --attr-id downloads \
  --regex '(v[\d.]+).*(https://[^"'"']+)'

vendor-config list
vendor-config remove --vendor Canon
```

Look up firmware for a target using saved vendor config:

```bash
firmware-lookup --target-id 1
```

Test firmware lookup with runtime URL/regex inputs:

```bash
firmware-lookup \
  --target-id 1 \
  --url-template 'https://example.com/{alias}/firmware' \
  --attr-id downloads \
  --regex '(v[\d.]+).*(https://[^"'"']+)'
```

### Development

Run the full test suite:

```bash
python -m pytest -q
```
