# Search Vulnerabilities Command Design

## Context

Add a read-only slash command to the Discord bot that queries stored vulnerabilities with optional filters by year and by collection time. This lets users look up what the bot has already collected without triggering a new sync.

## Decisions

- **Read-only command.** Open to all users (no admin role required).
- **In-memory filtering.** Uses `ExportService.snapshot()` + `group_findings()` and filters the results in the application layer. No new repository methods needed. Can add repository-level queries later if dataset size warrants it.
- **Multi-message pagination.** Discord limits 10 embeds per message. The bot sends multiple follow-up messages, 10 embeds each.
- **Collected time = `Vulnerability.created_at`.** This is the moment the bot stored the record in the database.
- **Year filter matches either** CVE/advisory ID year (e.g. the `2024` in `CVE-2024-12647` or `ZDI-24-280`) **or** `published_date.year` when available. A vulnerability matches if either one equals the requested year.
- **Default time range: today.** When no `from_date` or `to_date` is provided, the command returns vulnerabilities stored today (`created_at` within the current UTC date).

## Slash Command

| Command | Description | Admin-only |
|---|---|---|
| `/search-vulns [year] [from_date] [to_date]` | Search stored vulnerabilities by year and/or collection date range | No |

All parameters are optional:
- `year` — integer (e.g. `2024`). Matches ID year or published year.
- `from_date` — inclusive start date in `YYYY-MM-DD` format. Filters on `created_at`.
- `to_date` — inclusive end date in `YYYY-MM-DD` format. Filters on `created_at`.

When no date parameters are provided at all, the default is today's UTC date (i.e. `from_date=today`, `to_date=today`).

When `year` and date parameters are both provided, both filters apply (AND logic).

## Filtering Logic

1. Call `ExportService.snapshot()` and `group_findings()` to get the full list of finding dicts (same as `/sync-cves` and the daily report).
2. Apply **year filter** if `year` is given: keep findings where `advisory_id` contains the year (e.g. `CVE-{year}-` or `ZDI-{short_year}-`) **or** the `published_date` field's year matches. For 2-digit ZDI years (`ZDI-24-...`), the 4-digit `year` parameter is compared to `2000 + short_year`.
3. Apply **date filter** if `from_date` and/or `to_date` are given: keep findings where the underlying `Vulnerability.created_at` falls within the range (inclusive of both endpoints, using UTC dates). Since `group_findings` doesn't currently include `created_at`, the handler needs access to the raw vulnerability objects to check this — it can look them up from `vulnerability_repo.list_all()` by `advisory_id`.
4. If no `year` and no date parameters are given, default to today's UTC date range.

## Response Format

Summary line:

```
Found 15 vulnerabilities (year: 2024, collected: 2026-05-01 to 2026-05-21)
```

Then one embed per vulnerability using the existing `build_finding_embed()`, sent in batches of 10 per message. If the total exceeds 10, the summary line includes `showing 1-10 of 15` and subsequent messages continue the count.

## Error Handling

- Invalid date format: reply with an ephemeral message explaining the `YYYY-MM-DD` format.
- No results: reply with a text message "No vulnerabilities found matching the filters."
- Year out of reasonable range (< 1999 or > current year + 1): ephemeral error.
- The command never crashes the bot; all errors are caught and returned as messages.

## Architecture

No new files needed. Changes are confined to:

- `src/updater/presentation/discord_bot/commands.py` — add `handle_search_vulns` async handler.
- `src/updater/presentation/discord_bot/bot.py` — register `/search-vulns` slash command, wire to handler.
- `tests/presentation/discord_bot/test_commands.py` — add tests for the new handler.

The handler follows the same pattern as existing commands: takes `Services`, returns `CommandResult`. The bot.py command wrapper sends multiple messages for pagination (similar to how `_run_notify` sends embeds one by one).

## Testing

- Unit-test the handler with fake repositories:
  - Year filter matches CVE ID year.
  - Year filter matches ZDI short year (ZDI-24 → 2024).
  - Year filter matches `published_date` year when ID doesn't contain the year.
  - Date range filter on `created_at`.
  - Default to today when no params given.
  - AND logic when both year and date are provided.
  - No results returns appropriate message.
- No live Discord API tests.
