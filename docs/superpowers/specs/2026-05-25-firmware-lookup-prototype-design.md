# Firmware Lookup Prototype Design

## Goal

Build a CLI prototype that finds the newest firmware version and download URL for an existing target. The user selects a target by the same numbered ID shown by `/list-targets`; the lookup uses a per-target vendor-defined alias and a per-vendor crawler configuration to fetch and parse the vendor firmware page.

## User Inputs

The lookup input is:

- `target-id` — 1-based target number from the alphabetically sorted target list.

Crawler setup is defined by an administrator and stored before lookup. This is how the required URL, attribute ID, and regex inputs are supplied for each vendor rather than re-entered for every target lookup:

- `vendor` — vendor name matching `Target.vendor`.
- `url_template` — HTTPS vendor URL template containing `{alias}`, for example `https://vendor.example/downloads/{alias}/firmware`.
- `attr_id` — HTML element ID to locate on the crawled page.
- `regex` — regular expression applied to the located element's inner HTML. Capture group 1 is the firmware version; capture group 2 is the firmware download URL.

Each target also stores:

- `vendor_alias` — vendor-defined product slug/model identifier that replaces `{alias}` in the vendor URL template.

## Data Model

Add `vendor_alias: str | None` to `Target`.

Add a new `VendorConfig` domain model:

```python
@dataclass
class VendorConfig:
    vendor: str
    url_template: str
    attr_id: str
    regex: str
    id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
```

Add a `VendorConfigRepository` protocol with:

- `upsert(config: VendorConfig) -> VendorConfig`
- `find_by_vendor(vendor: str) -> VendorConfig | None`
- `list_all() -> list[VendorConfig]`
- `delete(vendor: str) -> bool`

MongoDB stores vendor configs in `vendor_configs` with a unique normalized vendor index.

## Lookup Flow

`FirmwareLookupService.lookup(target_id: int)` performs:

1. Load all targets sorted exactly like `/list-targets`.
2. Resolve `target_id` as a 1-based index into that list.
3. Reject invalid IDs with a clear range error.
4. Require the target to have `vendor`, because vendor config lookup depends on it.
5. Require the target to have `vendor_alias`, because the vendor URL template needs it.
6. Load `VendorConfig` for the target's vendor.
7. Require `url_template` to use HTTPS and contain `{alias}`.
8. Render the URL by safely URL-encoding the target's `vendor_alias` as one path/query replacement value.
9. Use the browser adapter to navigate to the rendered URL and return the inner HTML of the element matching `#attr_id`.
10. Apply the config regex to the element inner HTML.
11. Require at least one match with capture groups 1 and 2.
12. Resolve a relative captured download URL against the rendered vendor page URL; require the resulting URL to use HTTPS.
13. Return target name, vendor, rendered URL, firmware version, download URL, and the matched HTML snippet.

## Browser Adapter

Use a small browser boundary so service tests do not need a real browser:

```python
class BrowserAdapter(Protocol):
    def fetch_element_html(self, url: str, element_id: str) -> str: ...
```

The prototype implementation will use Playwright with CloakBrowser integration behind this adapter. If the CloakBrowser Python API is not available in the local environment during implementation, the adapter should keep the integration point isolated and fail with an actionable dependency message rather than leaking package-specific code into the service.

## CLI Prototype

Add two console scripts.

### `firmware-lookup`

```bash
firmware-lookup --target-id 2
```

Loads `.env`, connects to MongoDB, runs `FirmwareLookupService`, and prints:

```text
Target: Canon MF654Cdw
Vendor: Canon
Resolved URL: https://vendor.example/downloads/canon-mf654cdw/firmware
Firmware Version: 2.1.0
Download URL: https://vendor.example/files/canon-mf654cdw-2.1.0.bin
```

### `vendor-config`

```bash
vendor-config add --vendor "Canon" --url-template "https://vendor.example/downloads/{alias}/firmware" --attr-id "firmware" --regex "Version ([^<]+).*href=\"([^\"]+)\""
vendor-config list
vendor-config remove --vendor "Canon"
```

The `add` command validates that the regex compiles and has at least two capture groups. It also validates that `url_template` uses HTTPS and contains `{alias}`. Vendor config management is administrator-controlled because the configured crawler URL determines which remote page the prototype visits.

## Target Alias Management

For the prototype, target vendor aliases are added through import data and repository support rather than a Discord command. The CSV importer should accept an optional `vendor_alias` column and persist it to `Target.vendor_alias`.

## Error Handling

User-facing errors should be explicit:

- Invalid target ID: show valid range.
- Target missing vendor: explain that vendor is required.
- Target missing vendor alias: explain that `vendor_alias` must be set for this target.
- Missing vendor config: explain which vendor needs a config.
- URL template not HTTPS or missing `{alias}`: reject config on add and lookup.
- Element not found: include the resolved URL and element ID.
- Regex has fewer than two capture groups: reject config on add.
- Regex does not match: include the element ID and resolved URL.
- Captured download URL is neither relative nor HTTPS: reject the result.
- Browser dependency or launch failure: return an actionable message naming Playwright/CloakBrowser setup.

## Tests

Add unit tests for:

- Target ID resolution follows `/list-targets` sorting.
- Missing vendor, missing vendor alias, and missing vendor config errors.
- URL template rendering with a URL-encoded `vendor_alias`.
- Regex group 1/group 2 extraction from element inner HTML.
- Relative captured download URL resolution and invalid non-HTTPS URL rejection.
- Invalid vendor config regex, non-HTTPS template, and missing `{alias}` validation.
- CSV import preserves optional `vendor_alias`.

Browser integration is tested through a fake `BrowserAdapter` in service tests. A real browser smoke test can be added after the CloakBrowser package API is confirmed locally.

## Scope

In scope for prototype:

- Domain model additions.
- MongoDB mapping and repository for vendor configs.
- CSV support for target `vendor_alias`.
- Firmware lookup application service.
- CLI scripts for lookup and vendor config management.
- Playwright/CloakBrowser browser adapter boundary.
- Unit tests with a fake browser adapter.

Out of scope for prototype:

- Discord slash command integration.
- Scheduled firmware checks and notifications.
- Persisting firmware lookup results into `target_versions`.
- Multi-vendor fallback or multiple aliases per target.
- Automatic newest-version comparison across multiple matches. The first regex match is treated as the newest result because the vendor-specific regex/config is responsible for selecting the desired page region.
