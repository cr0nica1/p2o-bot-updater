# Target Version Checkers Design

## Goal

Add on-demand **version checkers** for ten Pwn2Own targets so the existing
version-checker command (`firmware-lookup` / `/lookup-firmware`, plus new
`check-version` aliases) returns each target's current published version when
invoked. The version is extracted at call time from the exact vendor URL
supplied for each target.

Targets:

| # | Target | Exact URL |
|---|--------|-----------|
| 1 | Philips Hue Bridge Pro | https://www.philips-hue.com/en-us/support/release-notes/bridge-pro |
| 2 | Samsung Galaxy S26 | https://security.samsungmobile.com/securityUpdate.smsb |
| 3 | Home Assistant Green | https://github.com/home-assistant/operating-system/releases |
| 4 | OpenAI Codex | https://learn.chatgpt.com/docs/changelog?type=codex-cli |
| 5 | Anthropic Claude Code | https://code.claude.com/docs/en/changelog |
| 6 | Postgres pgvector | https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md |
| 7 | Oracle Autonomous AI Database | https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/autonomous-ai-database-updates.html |
| 8 | LiteLLM | https://docs.litellm.ai/release_notes/ |
| 9 | NVIDIA Dynamo | https://docs.nvidia.com/dynamo/reference/releases |
| 10 | Chroma | https://github.com/chroma-core/chroma/releases |

## Background: the existing engine

The current version checker is the firmware-lookup engine:

- `VendorConfig(vendor, url_template‹{alias}›, attr_id, regex)` stored per vendor
  (`vendor_configs` collection, unique on normalized vendor).
- `FirmwareLookupService.lookup(target_id)` sorts targets like `/list-targets`,
  resolves the target, requires `vendor` + `vendor_alias`, loads the vendor's
  config, renders the URL by substituting `{alias}`, fetches the inner HTML of
  the element `#attr_id` via a Playwright `BrowserAdapter`, applies `regex`, and
  returns **version (group 1)** + **download URL (group 2)**.
- Surfaced via `firmware-lookup`/`vendor-config` CLIs and `/lookup-firmware`,
  `/set-vendor-firmware`, etc. on Discord.

This engine assumes vendor **firmware pages** (a stable element `id` and a
downloadable binary). The ten targets above are heterogeneous release/changelog
pages, most with **no download URL** and **no reliable element `id`**, and three
targets currently share the vendor `Open Source`. The engine is therefore
**extended** (one schema, relaxed) rather than replaced.

## Decisions locked during brainstorming

1. **Extend the one config schema** (not a parallel subsystem). The legacy
   firmware path stays working untouched.
2. **On-demand only.** No scheduler / notify-on-new-version work in this change
   (the `TargetVersion` model exists for a future follow-up).
3. **Fetch the exact URL** given for each target.
4. **Per-target config resolution**, so each of the ten (including the three
   `Open Source` targets) points at its own URL/regex without vendor collisions.

## Reconnaissance findings (2026-08-17)

Each target's exact URL was probed. Key results:

- **All ten are server-rendered**: a plain HTTP GET (with a browser-like
  `User-Agent`) already contains the version — including the GitHub React pages
  (blob + releases) and the Docusaurus/Mintlify/Fern docs. Therefore **every
  seed checker uses `fetch = http`**; no headless browser is required for these
  ten. Browser mode remains available for the legacy firmware path and as a
  fallback.
- **A browser-like `User-Agent` is mandatory** for the HTTP fetch; some hosts
  reject the default `python-requests` UA.
- **GitHub unauthenticated requests are rate-limited** (~60/hr/IP). Acceptable
  for on-demand lookups; noted as a risk.
- **"Newest entry" is not always the first version on the page.** Recon found a
  specific trap per target, addressed by anchored regexes plus a match-selection
  strategy (see below). Notably:
  - **pgvector**: first `## x.y.z` heading is `0.8.7 (unreleased)`; the newest
    *released* version is `0.8.6`. The regex requires a `(YYYY-MM-DD)` date.
  - **Oracle**: the visible update list lags (ends at `23.26.2`); the true
    latest `23.26.3` only appears in a nav link (`…release-update-23.26.3.html`).
    Requires **`select = max`** across body + nav matches.
  - **Claude Code / LiteLLM / Dynamo / Chroma / Codex / HA Green**: nav tokens,
    generator versions, prerelease/rc/dev tags, or lagging tables must be
    excluded by anchoring the regex to the entry markup.

**Policy:** checkers report the **newest stable, publicly released** version,
excluding unreleased / rc / dev / alpha / prerelease entries.

## Data model changes

Extend `VendorConfig` (in `src/updater/domain/models.py`) with optional fields,
all defaulted so existing rows, mappings, and tests are unaffected:

```python
@dataclass
class VendorConfig:
    vendor: str
    url_template: str
    attr_id: str = ""                     # now optional (legacy #id path)
    regex: str = ""                       # group 1 = version; group 2 = download URL (optional)
    target: str | None = None            # bind to a specific target (normalized name); None = vendor-keyed
    fetch: str = "browser"               # "browser" (default, legacy) | "http"
    selector: str | None = None          # optional CSS selector; falls back to #attr_id, then whole document
    select: str = "first"                # match selection: "first" | "last" | "max"
    id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def normalized_vendor(self) -> str: ...
    @property
    def normalized_target(self) -> str | None: ...   # normalize_name(target) if target else None
```

Relaxed validation (`validate_vendor_inputs`):

- `url_template` must be HTTPS.
- `{alias}` is now **optional**. If present, the target must have `vendor_alias`
  (legacy behavior). If absent, the URL is used verbatim.
- `regex` must compile and have **≥1 group**. Group 1 = version (required).
  Group 2 = download URL (optional); only validated/resolved when it matches.
- `fetch` ∈ {`browser`, `http`}; `select` ∈ {`first`, `last`, `max`}.

MongoDB mapping (`mongo.py`) persists the new fields. Resolution index: keep the
unique index on `normalized_vendor` for vendor-keyed rows; add a partial/unique
index on `normalized_target` for target-bound rows (rows may set `target` and/or
`vendor`). `VendorConfigRepository` gains:

- `find_for_target(target: Target) -> VendorConfig | None` — returns the
  target-bound config first (match on `normalized_target`), else the vendor-bound
  config (`find_by_vendor(target.vendor)`).

## Fetch adapters

One fetch protocol, two implementations, selected per config by `fetch`.

```python
class FetchAdapter(Protocol):
    def fetch_html(self, url: str, selector: str | None) -> str: ...
```

- **`HttpFetchAdapter`** (new, `infrastructure/browser/http_fetch.py`) — the
  workhorse for all ten targets. Uses `requests.get` with a browser-like
  `User-Agent` and a timeout. If `selector` is given, parse with BeautifulSoup
  and return `soup.select_one(selector)`'s HTML (raise a clear error if absent);
  otherwise return the full response text. Raises an actionable error on non-2xx
  / network failure.
- **`CloakBrowserAdapter`** (existing) — generalized so `fetch_html(url,
  selector)` supports a CSS `selector` or the whole rendered page, not only
  `#id`. Its legacy `fetch_element_html(url, element_id)` is retained (delegates
  to `fetch_html(url, f"#{element_id}")`) so nothing downstream breaks.

`FirmwareLookupResult.download_url` becomes `str | None`.

## Lookup service changes

In `FirmwareLookupService` (`application/firmware_lookup.py`):

- Constructor takes both adapters (or a small factory) and picks by
  `config.fetch`; default stays browser for legacy configs.
- `lookup(target_id)` resolves config via `vendor_config_repo.find_for_target`
  (target-first, vendor fallback). Missing config → clear error.
- Fetch space = `selector` result, else `#attr_id` (legacy), else whole document.
- **Match selection** applies `re.finditer` and picks by `config.select`:
  - `first` → first match (default; current behavior).
  - `last` → last match.
  - `max` → the match whose group 1 compares greatest under a **version-aware
    key** (split group 1 into numeric components on non-digit separators and
    compare as an int tuple; fall back to string for non-numeric parts).
- Version = group 1 (stripped). Download URL = group 2 if the regex has ≥2
  groups and it matched (resolved against the page URL, must be relative or
  HTTPS); otherwise `None`.

`{alias}`-less URLs skip `vendor_alias` requirement and URL rendering.

## The ten version-determination sets

Each is one config row bound to its target via `target`, `fetch = http`,
`selector = None` (regex runs against the whole response; anchoring is inside the
regex). Regexes are Python `re` with `re.DOTALL` where a `[\s\S]*?` bridge is
used. `current` = the value verified during recon on 2026-08-17. Exact regexes
are re-validated against a captured fixture during implementation (§Testing).

| Target | `select` | `regex` (group 1 = version) | current |
|--------|----------|------------------------------|---------|
| Philips Hue Bridge Pro | first | `Software version\s+(\d{10})` | `2071401010` |
| Samsung Galaxy S26 | first | `(?i)SMR[ -]((?:Jan\|Feb\|Mar\|Apr\|May\|Jun\|Jul\|Aug\|Sep\|Oct\|Nov\|Dec)-20\d{2}\s+Release\s+\d+)` | `Aug-2026 Release 1` |
| Home Assistant Green | first | `releases/tag/(\d+\.\d+(?:\.\d+)?)"` | `18.2` |
| OpenAI Codex | first | `@openai/codex@(\d+\.\d+\.\d+)` | `0.147.0` |
| Anthropic Claude Code | first | `data-component-part="update-label"[^>]*>\s*(\d+\.\d+\.\d+)` | `2.1.233` |
| Postgres pgvector | first | `##\s+(\d+\.\d+\.\d+)\s+\(\d{4}-\d{2}-\d{2}\)` | `0.8.6` |
| Oracle Autonomous AI Database | **max** | `(?:Release Update\s+\|release-update-)(\d+(?:\.\d+){1,2})` | `23.26.3` |
| LiteLLM | first | `id=latest-release[\s\S]*?/release_notes/(v\d+\.\d+\.\d+)/` | `v1.97.0` |
| NVIDIA Dynamo | first | `Latest\s*\((v\d+\.\d+\.\d+)\)` | `v1.4.0` |
| Chroma | first | `releases/tag/(\d+\.\d+\.\d+)(?=["/#?])` | `1.5.9` |

> In the table above, `\|` is a markdown-escaped `|` (regex alternation); the
> actual pattern uses a bare `|`.

Notes and rationale per target:

- **Philips Hue Bridge Pro** — 10-digit internal build number, newest-first;
  entries occasionally pair two builds with a slash. No download URL (OTA).
- **Samsung Galaxy S26** — this URL is the *general* Samsung SMR bulletin (no
  per-device selector); the newest monthly SMR is the effective S26 patch level.
  Version displayed as `SMR ` + group 1. No download URL.
- **Home Assistant Green** — the trailing `"` in the regex excludes prereleases
  like `18.2.rc1`. A real download asset exists
  (`releases/download/18.2/haos_green-18.2.img.xz`) — deferred as a future
  group-2 enhancement, not part of the seed.
- **OpenAI Codex** — `?type=…` is a client-side filter, so the HTTP response
  interleaves products; anchoring on `@openai/codex@` is Codex-CLI-specific and
  yields the stable line (excludes the `-alpha` stream).
- **Anthropic Claude Code** — anchor to the Mintlify `update-label`; nav tokens
  appear earlier in the document. Fallback source if markup churns:
  `raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md`.
- **Postgres pgvector** — content is server-embedded in GitHub's blob HTML;
  requiring a `(YYYY-MM-DD)` date skips `0.8.7 (unreleased)`.
- **Oracle** — body list is oldest-first *and lags*; the newest RU appears only
  in the nav filename. The regex matches both `Release Update 23.26.2` and
  `release-update-23.26.3.html`; `select = max` returns `23.26.3`. Lowest
  confidence target — flagged as a risk.
- **LiteLLM** — anchor to `#latest-release` to avoid the Docusaurus generator
  `v3.8.1` and the sidebar `rc1`.
- **NVIDIA Dynamo** — use the version dropdown (`Latest (vX.Y.Z)`); the stats
  table lags. A download URL exists on the timeline but would invert group order,
  so it's deferred.
- **Chroma** — digit-anchored tag regex selects the bare-semver core release,
  skipping `cli-*`, `foundation-cli-*`, and the rolling `latest` dev tag.

## Command surface (reuse the original commands)

- `vendor-config add` gains optional flags: `--target`, `--fetch {http,browser}`,
  `--selector`, `--select {first,last,max}`; `--attr-id` becomes optional; the
  regex may have 1+ groups. `vendor-config list` shows the new fields.
- `firmware-lookup --target-id N` prints **Version** always, and **Download URL**
  only when present.
- Discord `/set-vendor-firmware` and `/lookup-firmware` gain the same optional
  parameters and the version-only output.
- **Aliases** `version-config` (CLI) and `/check-version` (Discord) map to the
  same handlers so the naming reads correctly for software targets. The
  `firmware-*` names are retained for backward compatibility.

## Seeding the ten targets

- Extend the vendor-firmware CSV importer with the new columns (`target`,
  `fetch`, `selector`, `select`; `attr_id`/download optional).
- Ship `samples/version_checks.csv` with all ten rows above.
- Provide a small seed path (CSV import or script) that upserts the ten
  **targets** under the task's canonical names — note discrepancies with the
  current `samples/targets.csv`: `Phillips Hue Bridge`→`Philips Hue Bridge Pro`,
  `Home Assistant`→`Home Assistant Green`, and the `Oracle Automatous AI
  Database` typo — and binds each config to its target. Existing vendors are left
  as-is; per-target binding makes the shared `Open Source` vendor a non-issue.

## Testing

- **One fixture-backed unit test per target**: capture the real page's response
  into `tests/fixtures/version/<target>.html` and assert the checker extracts the
  expected `current` value above (feeding the fixture through the regex +
  `select` logic, no network). Pins the brittle regexes and documents "what the
  page looked like."
- Service tests with fake `http`/`browser` fetch adapters: fetch-mode selection,
  `find_for_target` resolution (target-first, vendor fallback), `select`
  first/last/max (incl. version-aware max for Oracle-style values), version-only
  (1-group) regex, optional download resolution, `{alias}`-less URLs.
- Validation tests: HTTPS enforced, ≥1 group required, invalid `fetch`/`select`
  rejected.
- Backward-compat tests: an existing firmware config (`attr_id` + 2-group regex,
  browser fetch) still resolves and returns version + download URL.

## Error handling

- Config not found for target → name the target and that no version check is
  configured.
- Fetch failure (non-2xx / network / browser launch) → actionable message naming
  the URL and fetch mode.
- Selector not found → include selector + URL.
- Regex no match → include URL and (masked) regex.
- Version-only match → skip download resolution silently.

## Backward compatibility

- New `VendorConfig` fields are optional with legacy defaults (`fetch=browser`,
  `select=first`, `attr_id`/`selector`/`target` empty). Existing rows load and
  behave exactly as before.
- Legacy `fetch_element_html` retained on the browser adapter.
- `firmware-*` command names and Discord commands unchanged; new flags optional.

## Scope

In scope:

- `VendorConfig` extension + Mongo mapping/index + `find_for_target`.
- `HttpFetchAdapter`; browser adapter selector generalization.
- Lookup service: per-target resolution, fetch selection, `select` strategy,
  optional download.
- CLI/Discord flag extensions + `version-config` / `check-version` aliases.
- Ten seed configs + `samples/version_checks.csv` + target seeding + per-target
  fixture tests.

Out of scope (future follow-ups):

- Scheduler / notify-on-new-version and persisting into `target_versions`.
- Cross-run version diffing / history.
- Download-URL capture for HA Green and Dynamo (group-2 enhancement).
- Per-device Samsung rollout confirmation (lives on a different Samsung page).

## Risks

- **Oracle** page lag + oldest-first ordering makes it the least robust checker;
  mitigated with `select = max` over body + nav, flagged as medium confidence.
- **Markup churn** on React/docs pages can break regexes; mitigated by
  whole-document anchored regexes, fixtures, and documented fallbacks (e.g.
  GitHub raw CHANGELOG for Claude Code).
- **GitHub rate limits** on unauthenticated fetches (HA Green, pgvector, Chroma);
  acceptable for on-demand use.
- **Prerelease drift**: streams like Codex `-alpha`, LiteLLM `rc`, Chroma `dev`
  are intentionally excluded; if the policy should track prereleases, the regex
  anchors change.
