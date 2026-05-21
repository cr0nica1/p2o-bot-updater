## Goal

Replace the name-based `/show-target` Discord command with a numbered-ID lookup so users can reference targets from `/list-targets` output, and display vulnerability details with an optional limit on count.

## Changes

### `/list-targets`

Show targets as a numbered list, sorted alphabetically by name:

```text
Targets:
1. Adobe Reader
2. Canon MF654Cdw
3. VMware Workstation
```

### `/show-target`

Replace the `name: str` parameter with `target_id: int` and an optional `limit: int` parameter.

- `target_id` — 1-based index into the alphabetically sorted target list (same order `/list-targets` uses). If out of range, return an error message.
- `limit` — optional. When set, show only the N most recent vulnerabilities. When omitted, show all vulnerabilities.

Response format:

```text
Target #2: Canon MF654Cdw
Aliases: Canon imageCLASS MF654Cdw
Vendor: Canon
Category: printer
Showing 10 of 30 vulnerabilities
```

Followed by vulnerability embeds using existing `build_finding_embed()`.

### Sorting for "recent"

Vulnerabilities sorted by `published_date` descending (newest first). Fall back to `created_at` when `published_date` is absent.

### Error handling

- `target_id` out of range → `"Invalid target ID. Use /list-targets to see available targets (1-N)."`
- Target has no vulnerabilities → show target metadata with `"No vulnerabilities found."`
- `limit` ≤ 0 → treated as "show all"

## Scope

- `handle_list_targets` in `commands.py` — add numbering
- `handle_show_target` in `commands.py` — accept `target_id` + `limit`, resolve target, fetch and sort vulnerabilities
- Slash command definition in `bot.py` — change parameter from `name: str` to `target_id: int`, add `limit: int | None`
- Tests — update existing tests, add new test cases for ID lookup and limit
