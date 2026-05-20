# Discord Bot Design

## Context

Replace the CLI interface (`updater`) with a Discord bot that provides the same functionality through slash commands, adds scheduled daily sync/notification, and allows manual vulnerability entry.

## Decisions

- **Fully replaces the CLI.** The `updater` CLI entrypoint is removed.
- **Single Discord server/channel.** No multi-server support.
- **Admin-only commands.** Only users with the configured admin role can run protected commands. Read-only commands (`show-target`, `list-targets`, `show-schedule`) are open.
- **discord.py** with slash commands via `app_commands`.
- **Fixed daily schedule.** One sync time + one notification time per day.
- **.env config file** for token, guild, channel, role, schedule times. `/set-schedule` updates `SYNC_TIME` and `NOTIFY_TIME` in this file.
- **Background scheduler** using `discord.ext.tasks` checking every 60 seconds.
- **Thin Discord layer** over existing application services (ImportTargetsService, SyncVulnerabilitiesService, ExportService) and MongoDB repositories. Domain/application/infrastructure code is mostly unchanged; small additions needed:
  - `TargetRepository.delete(name)` method for `/remove-target` (currently only `delete_all()` exists).
  - `TargetVulnerabilityRepository.delete_by_target(target_id)` to clean up links when removing a target.

## Slash Commands

| Command | Description | Admin-only |
|---|---|---|
| `/import-targets` | Upload CSV file, import targets | Yes |
| `/add-target` | Add a single target (name, optional aliases/vendor/category) | Yes |
| `/remove-target` | Remove one or more targets by name | Yes |
| `/show-target <name>` | Show target details and linked vulnerability count | No |
| `/list-targets` | List all targets | No |
| `/add-vuln` | Manually add a vulnerability (advisory_id, description, cvss_score, severity, optional references/target_name). If target_name given, also creates a TargetVulnerability link. | Yes |
| `/sync-cves [target]` | Manually sync vulnerabilities for all targets, or one target if `target` name is given | Yes |
| `/set-schedule <sync_time> <notify_time>` | Set daily sync time and notification time (HH:MM format). Updates `.env` file at runtime; scheduler re-reads on next check. | Yes |
| `/show-schedule` | Show current schedule config | No |

## Configuration (.env)

```
DISCORD_TOKEN=...
DISCORD_GUILD_ID=...
DISCORD_CHANNEL_ID=...
DISCORD_ADMIN_ROLE_ID=...
SYNC_TIME=08:00
NOTIFY_TIME=09:00
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=pwn2own_updater
```

Missing `DISCORD_TOKEN` or invalid time format on startup prints an error and exits.

## Architecture

```
src/updater/
  presentation/
    discord_bot/
      bot.py          -- Bot setup, scheduler, entrypoint
      commands.py     -- Slash command handlers
      permissions.py  -- Admin role check decorator
      formatting.py   -- Vulnerability finding -> Discord embed
  (existing, unchanged)
    application/      -- ImportTargetsService, SyncVulnerabilitiesService, ExportService
    domain/           -- models, repositories
    infrastructure/   -- mongo, nvd, zdi, csv_loader, json_exporter
```

The `updater` CLI entrypoint in `pyproject.toml` (`[project.scripts]`) is replaced with the bot entrypoint.

## Daily Schedule Flow

1. **SYNC_TIME**: Scheduler calls `SyncVulnerabilitiesService.sync_all()`. Errors are logged but do not crash the bot.
2. **NOTIFY_TIME**: Scheduler calls `ExportService.snapshot()`, formats findings, and posts to the configured channel.

The scheduler uses `discord.ext.tasks` with a 60-second loop that checks current time against configured SYNC_TIME and NOTIFY_TIME. It tracks whether sync/notify has already fired today to avoid duplicate runs.

MongoDB connection failure during a sync cycle is logged and skipped. Bot stays online and retries next cycle.

## Notification Format

The daily report starts with a summary message, then sends one separate Discord embed per finding to avoid message length limits.

Summary message:

```
Daily Vulnerability Report — 2026-05-20
Targets processed: 5
New findings: 3
Errors: 0
```

Each finding is one embed:

```
Title:  CVE-2024-12647        (or ZDI-26-280 if no CVE)
Target: Canon MF654Cdw, Canon MF656Cdw
Severity: HIGH
CVSS: 7.8
Description: Canon printer vulnerability detail from ZDI/NVD
References:
- https://example.com/advisory
- https://nvd.nist.gov/vuln/detail/CVE-2024-12647
```

Multiple targets affected by the same vulnerability are joined in the Target field under one embed.

## Severity Colors

Embed colors match NVD/CVE report convention:

| Severity | Color  | Hex       |
|---|---|---|
| Critical | Red    | `#CC0000` |
| High | Orange | `#FF7700` |
| Medium | Yellow | `#FFCC00` |
| Low | Green  | `#28A745` |
| Informational / None | Grey | `#999999` |

## Manual /sync-cves Response

The bot replies with an ephemeral message (visible only to the triggering user) in the same finding format, one embed per vulnerability found during the sync.

## Error Handling

- Sync errors (NVD/ZDI timeouts, parse failures) are collected and reported in the notification or command response. Bot does not crash.
- Invalid `.env` on startup (missing DISCORD_TOKEN, bad time format) prints error and exits without starting.
- MongoDB connection failure during sync: log and skip cycle, retry next time. Bot stays online.

## Testing

- Unit-test command handlers with fake repositories/services (no live Discord API).
- Unit-test permission checks for admin role enforcement.
- Unit-test schedule time parsing and "should fire now" logic.
- Unit-test notification formatting:
  - CVE ID title when CVE exists, ZDI ID title when CVE does not exist.
  - Severity color mapping.
  - One embed per finding.
  - Multiple affected targets joined in Target field.
- Source tests for NVD/ZDI remain unchanged.
- No live Discord API tests; use fake bot/channel objects.

## Dependencies to Add

- `discord.py>=2.3.0`
- `python-dotenv>=1.0.0`
