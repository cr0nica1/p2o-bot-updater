# Pwn2Own updater — data quality audit

| Field | Value |
|---|---|
| Date | 2026-08-19 |
| Database | `pwn2own_updater` @ `mongodb://localhost:27017` |
| Scope | Missed CVEs, wrong/stale latest versions, integrity |
| Method | Live `/check-version` path, GitHub/npm APIs, NVD 2.0 keyword search vs stored links |

This is a snapshot of what is in Mongo **today**, compared to vendor pages and NVD. It is not a full NVD/ZDI recrawl of every alias.

---

## 1. Verdict

The database is **structurally healthy** (no orphans, no duplicate IDs, versions resolve to real targets). Software latest-versions match vendor sources.

The gaps are **search quality** and **one version meaning**:

- **~46+ real CVEs never stored** because seed used long official names and no aliases (`Claude Code`, `pgvector`).
- **~17 Chroma rows are false positives** (FFmpeg / Razer / ChromeOS “chroma”).
- **Samsung Galaxy S26 version is the global SMR bulletin**, not an S26 firmware string. The page does not mention S26.
- **Incremental NVD sync 404s** for any target that already has a 2026 CVE (`pubStartDate` without `pubEndDate`). New NVD CVEs for those targets will not land.

---

## 2. Inventory (healthy)

| Collection | Count | Integrity |
|---|---|---|
| `targets` | 11 | Unique `normalized_name`. No duplicates. |
| `vendor_configs` | 11 | One checker bound to each target (Oura included). |
| `target_versions` | 12 | All `target_id`s resolve. One `is_latest` per target. |
| `vulnerabilities` | 78 | Unique `advisory_id`. Sources: NVD 73, ZDI 7 (2 overlap). |
| `target_vulnerabilities` | 78 | 0 orphan target IDs, 0 orphan vuln IDs, 0 unlinked vulns. |

Leftover empty database `p2o` exists with the same collection names and **0 documents**. The bot `.env` points at `pwn2own_updater` only. Harmless.

Indexes present: unique `targets.normalized_name`, `vulnerabilities.advisory_id`, `(target_id, vulnerability_id)`, partial unique versions, unique `vendor_configs.normalized_vendor`.

**Last writes**

- Latest vuln `created_at`: **2026-08-18 04:17 UTC** — no CVE written on 2026-08-19.
- Version scan `last_seen`: **2026-08-19 01:04 UTC** (08:04 UTC+7) — daily version pass did run.

---

## 3. Latest versions

Live lookup used the same `FirmwareLookupService` path as `/check-version`. Independent check used GitHub Releases/tags or npm `latest`.

| Target | DB latest | Live checker | Independent | Verdict |
|---|---|---|---|---|
| Anthropic Claude Code | 2.1.235 | 2.1.235 | npm `@anthropic-ai/claude-code` 2.1.235 | OK |
| Chroma | 1.5.9 | 1.5.9 | GitHub `chroma-core/chroma` tag `1.5.9` | OK |
| Home Assistant Green | 18.2 | 18.2 | GitHub `home-assistant/operating-system` `18.2` | OK |
| LiteLLM | v1.97.0 | v1.97.0 | GitHub `BerriAI/litellm` `v1.97.0` | OK |
| NVIDIA Dynamo | v1.4.0 | v1.4.0 | GitHub `ai-dynamo/dynamo` `v1.4.0` | OK |
| OpenAI Codex | 0.148.0 | 0.148.0 | npm `@openai/codex` 0.148.0 | OK |
| Oracle Autonomous AI Database | 23.26.3 | 23.26.3 | same Oracle page / regex | OK (self-consistent) |
| Oura Ring 5 | 2.1.3 | 2.1.3 | same Oura support page / regex | OK (self-consistent) |
| Philips Hue Bridge Pro | 2071401010 | 2071401010 | same Hue release-notes page | OK (self-consistent) |
| Postgres pgvector | 0.8.6 | GitHub HTML 429 | GitHub tags `v0.8.6` | OK |
| Samsung Galaxy S26 | Aug-2026 Release 1 | Aug-2026 Release 1 | Samsung SMR bulletin; **page has no “S26”** | **Wrong kind of version** |

Claude Code has two version rows (`2.1.234` previous, `2.1.235` latest). That is expected history, not a duplicate latest.

### 3.1 Samsung — wrong meaning, not a stale number

Checker regex:

```text
(?i)SMR[ -]((?:Jan|…|Dec)-20\d{2}\s+Release\s+\d+)
```

URL: `https://security.samsungmobile.com/securityUpdate.smsb`

The first match is the **global** “SMR Aug-2026 Release 1” paragraph. The HTML snippet around the match is the Samsung-wide bulletin (Google patches + SVE list). Strings `S26`, `Galaxy S26`, `SM-S93`, `SM-S94` are **absent**.

So the stored value is this month’s Samsung Mobile SMR label, not a Galaxy S26 firmware / One UI / AP build.

### 3.2 pgvector live fetch

`https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md` returned **HTTP 429** during this audit. Stored `0.8.6` still matches the latest GitHub tag `v0.8.6`. Treat the 429 as source flakiness, not a wrong version.

---

## 4. CVE coverage vs NVD

The tool searches **exact** `keywordSearch=<target.name>` only. Seeded targets have **empty `aliases`**. `samples/targets.csv` aliases were never imported.

### 4.1 Per-target scoreboard

| Target | Stored | Tool query (exact) | Better query | Missed (real) | Extra / junk |
|---|---:|---:|---|---|---|
| Anthropic Claude Code | 0 | `Anthropic Claude Code` → 0 | `Claude Code` → 44 | **~39–44 Claude Code CVEs** | a few “claude-code-router” / adjacent |
| Chroma | 24 | `Chroma` → 24 | `ChromaDB` → 7 (all already in DB) | 0 ChromaDB | **~17 false positives** |
| Home Assistant Green | 4 (all ZDI) | `Home Assistant Green` → 0 | `Home Assistant` → ~45 | 0 Green-specific NVD; HA *Core* is a scope call | — |
| LiteLLM | 30 | `LiteLLM` → 30 | `BerriAI litellm` ⊂ stored | 0 | 0 |
| NVIDIA Dynamo | 15 | `NVIDIA Dynamo` → 15 | — | 0 | 0 |
| OpenAI Codex | 4 (3 NVD + 1 ZDI) | `OpenAI Codex` → 3 | — | 0 NVD | ZDI-26-305 is extra vs NVD, valid ZDI |
| Oracle Autonomous AI Database | 0 | 0 | `Autonomous AI Database` → 0 | none published | — |
| Oura Ring 5 | 0 | 0 | `Oura Ring` → 0 | none published | — |
| Philips Hue Bridge Pro | 1 | `Philips Hue Bridge Pro` → 1 | `Philips Hue Bridge` → 11 | **8× 2026 Hue Bridge** (may apply to Pro) | 2 older non-Pro (2017, 2020) |
| Postgres pgvector | 0 | `Postgres pgvector` → 0 | `pgvector` → 6 | **CVE-2026-3172, CVE-2026-18022** | 4 adjacent (LlamaIndex, LangChain4j, …) |
| Samsung Galaxy S26 | 0 | 0 | 0 | none published | — |

### 4.2 Missed — Claude Code (high confidence)

`"Anthropic Claude Code"` exact = **0**. `"Claude Code"` exact = **44**. Sample descriptions start with “Claude Code is an agentic coding tool…” (~39/44 mention Anthropic / Claude Code).

Examples **not in Mongo**:

- CVE-2025-52882
- CVE-2025-54794
- CVE-2025-54795
- CVE-2025-55284
- CVE-2025-58764
- CVE-2025-59041
- CVE-2025-59828
- … (~36 more)

Root cause: search query is the seeded display name, not alias `claude code` from `samples/targets.csv`.

### 4.3 Missed — pgvector (high confidence)

| CVE | In DB? | Notes |
|---|---|---|
| CVE-2026-3172 | **No** | Buffer overflow in pgvector 0.6.0–0.8.1 |
| CVE-2026-18022 | **No** | IVFFlat wraparound, fixed in 0.8.6 |
| CVE-2024-23751 | No | LlamaIndex Text-to-SQL — mentions pgvector, not the extension |
| CVE-2026-25211 | No | Llama Stack logs pgvector password |
| CVE-2026-55405 | No | LangChain4j embedding store |
| CVE-2026-60090 | No | PraisonAI PGVector backend |

Root cause: query `Postgres pgvector` vs product name `pgvector`.

### 4.4 Possible miss — Philips Hue Bridge 2026

Stored: **CVE-2026-73669** only (Hue **Bridge Pro** MQTT).

`"Philips Hue Bridge"` also returns CVE-2026-3555 … CVE-2026-3562 (Zigbee / HomeKit RCE and auth bypass). Those say “Philips Hue Bridge”, not “Bridge Pro”. They are **not stored**. Whether they affect Pro is unconfirmed; the tool never searched the shorter name.

Older non-Pro: CVE-2017-14797, CVE-2020-6007 (model 2.X / BSB002).

### 4.5 Not missed

- Oracle, Oura, Samsung S26: NVD has no hits even with shorter names.
- LiteLLM, NVIDIA Dynamo, OpenAI Codex NVD sets match the tool query (no extra NVD IDs).
- Home Assistant Green has no NVD hits under that SKU. The 4 stored rows are ZDI-26-560…563. Pulling all “Home Assistant” Core CVEs would mix a different product.

---

## 5. Wrong CVEs already stored

### 5.1 Chroma false positives (~17 of 24)

All 7 `"ChromaDB"` NVD hits **are** in the DB (good):

- CVE-2024-45848 (MindsDB + ChromaDB integration — borderline)
- CVE-2026-45829, CVE-2026-45830, CVE-2026-45831, CVE-2026-45832, CVE-2026-45833
- CVE-2026-8828 (ChromaDB Rust)

The other ~17 `"Chroma"` hits are **not** chroma-core / ChromaDB. Confirmed pre-2024 junk:

| CVE | Actual product |
|---|---|
| CVE-2012-0851, CVE-2013-2277, CVE-2015-8217, CVE-2018-7557, CVE-2026-65706 | FFmpeg / libavcodec “chroma format” |
| CVE-2020-16602, CVE-2021-30493, CVE-2021-30494 | Razer Chroma SDK / Synapse |
| CVE-2021-3941 | OpenEXR `ImfChromaticities` |
| CVE-2023-3739 | ChromeOS **Chromad** |
| CVE-2023-54353 | Chromacam |

Keyword exact-match on the single word `Chroma` is too broad.

### 5.2 Stored CVE split by target

| Target | Count | Quality |
|---|---:|---|
| LiteLLM | 30 | Real product |
| Chroma | 24 | ~7 real / ~17 junk |
| NVIDIA Dynamo | 15 | Real |
| Home Assistant Green | 4 | Real ZDI |
| OpenAI Codex | 4 | Real |
| Philips Hue Bridge Pro | 1 | Real Pro |
| Claude Code, Oracle, Oura, pgvector, S26 | 0 | Empty (see missed) |

Severity of the 78 stored rows: CRITICAL 8, HIGH 44, MEDIUM 18, LOW 8.

---

## 6. Incremental sync will keep missing new NVD CVEs

`SyncVulnerabilitiesService.sync_all()` sets `since_year` to the max CVE year already linked to that target. `NvdSource.search()` then sends:

```text
pubStartDate=2026-01-01T00:00:00.000
```

and **no** `pubEndDate`. NVD 2.0 requires both, max 120-day window. That request returns **HTTP 404**.

`since_year` as of this audit:

| Target | NVD since | ZDI since | Effect |
|---|---|---|---|
| Chroma | 2026 | 2025 | NVD 404 |
| LiteLLM | 2026 | 2025 | NVD 404 |
| NVIDIA Dynamo | 2026 | — | NVD 404 |
| OpenAI Codex | 2026 | 2026 | NVD 404 |
| Philips Hue Bridge Pro | 2026 | — | NVD 404 |
| Home Assistant Green | — | 2026 | NVD full search (0 hits on official name) |
| Claude Code, Oracle, Oura, pgvector, S26 | — | — | NVD full search, but official name is 0 |

That matches **zero vulns created on 2026-08-19** even though the version scan ran.

---

## 7. Seed / metadata gaps (why searches miss)

Targets were created by `version-config seed`, which writes `Target(name, category)` only.

| Field | State |
|---|---|
| `aliases` | **[] on all 11** — CSV aliases unused |
| `vendor` | `Oura` on Oura Ring 5; **None** on the other 10 |
| `vendor_alias` | `claude code` on Claude Code only; unused by HTTP version checkers |

`samples/targets.csv` aliases that would have helped: `claude code`, `pgvector` is **not** in the CSV (`Postgres pgvector` has no alias), `Home Assistant`, `philips hue bridge`, `codex`, `Dynamo`, `litellm`.

---

## 8. Recommended fixes (not done in this audit)

1. **Import / set aliases** and search them: at least `Claude Code`, `pgvector`, `Philips Hue Bridge`. Re-sync those three targets (`sync_one`, no `since_year`).
2. **Delete or unlink Chroma junk** (FFmpeg / Razer / Chromad / OpenEXR / Chromacam). Prefer matching `ChromaDB` or `chroma-core`.
3. **Fix `NvdSource`**: if `since_year` is set, send `pubEndDate` and walk 120-day windows.
4. **Samsung**: do not treat the global SMR headline as S26 firmware. Find an S26-specific source or mark the checker as “Samsung SMR (not model firmware)”.
5. Optionally drop empty `p2o` database to avoid the next silent-empty-sync.

---

## 9. How this was checked

- Mongo: `pwn2own_updater` collections, indexes, link integrity, `since_year` via `SyncVulnerabilitiesService._compute_since_years`.
- Versions: `FirmwareLookupService.lookup` for all 11; GitHub `/releases/latest` or `/tags`; npm registry `latest` for Claude Code and Codex.
- NVD: `https://services.nvd.nist.gov/rest/json/cves/2.0` with `keywordSearch` ± `keywordExactMatch`, paced ~6 s/request.
- Samsung: fetched bulletin HTML; first regex match + `S26` / `SM-S9*` presence.

Audit time: 2026-08-19. NVD totals can move after this date.
