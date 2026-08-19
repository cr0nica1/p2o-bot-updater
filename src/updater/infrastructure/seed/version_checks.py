from __future__ import annotations

from updater.domain.models import Target, VendorConfig

# (name, aliases, vendor, category, search_names)
_TARGETS = [
    ("Philips Hue Bridge Pro", ["Philips Hue Bridge", "philips hue bridge"], "Signify", "Smart Home", []),
    ("Samsung Galaxy S26", ["samsung galaxy s26"], "Samsung", "Mobile Phone", []),
    ("Home Assistant Green", ["Home Assistant"], "Nabu Casa", "Smart Home", []),
    ("Oura Ring 5", [], "Oura", "Wellness", []),
    ("Chroma", [], "Open Source", "AI infrastructure", ["ChromaDB"]),
    ("Postgres pgvector", ["pgvector"], "Open Source", "AI infrastructure", []),
    ("Oracle Autonomous AI Database", [], "Oracle", "AI infrastructure", []),
    ("LiteLLM", ["litellm"], "Open Source", "AI infrastructure", []),
    ("NVIDIA Dynamo", [], "NVIDIA", "AI infrastructure", []),
    ("Anthropic Claude Code", ["Claude Code", "claude code"], "Anthropic", "Coding Agent", []),
    ("OpenAI Codex", [], "OpenAI", "Coding Agent", []),
]

# (target_name, url, select, regex)
_CHECKS = [
    ("Philips Hue Bridge Pro",
     "https://www.philips-hue.com/en-us/support/release-notes/bridge-pro",
     "first", r"Software version\s+(\d{10})"),
    ("Home Assistant Green",
     "https://github.com/home-assistant/operating-system/releases",
     "first", r'releases/tag/(\d+\.\d+(?:\.\d+)?)"'),
    ("OpenAI Codex",
     "https://learn.chatgpt.com/docs/changelog?type=codex-cli",
     "first", r"@openai/codex@(\d+\.\d+\.\d+)"),
    ("Anthropic Claude Code",
     "https://code.claude.com/docs/en/changelog",
     "first", r'data-component-part="update-label"[^>]*>\s*(\d+\.\d+\.\d+)'),
    ("Postgres pgvector",
     "https://raw.githubusercontent.com/pgvector/pgvector/master/CHANGELOG.md",
     "first", r"##\s+(\d+\.\d+\.\d+)\s+\(\d{4}-\d{2}-\d{2}\)"),
    ("Oracle Autonomous AI Database",
     "https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/autonomous-ai-database-updates.html",
     "max", r"(?:Release Update\s+|release-update-)(\d+(?:\.\d+){1,2})"),
    ("LiteLLM",
     "https://docs.litellm.ai/release_notes/",
     "first", r'id="?latest-release"?[\s\S]*?/release_notes/(v\d+\.\d+\.\d+)/'),
    ("NVIDIA Dynamo",
     "https://docs.nvidia.com/dynamo/reference/releases",
     "first", r"Latest\s*\((v\d+\.\d+\.\d+)\)"),
    ("Chroma",
     "https://github.com/chroma-core/chroma/releases",
     "first", r'releases/tag/(\d+\.\d+\.\d+)(?=["/#?])'),
    ("Oura Ring 5",
     "https://support.ouraring.com/hc/en-us/articles/34036777934227-Oura-Device-Firmware-Versions",
     "first", r"h2 id=[\s\S]{0,80}?Oura Ring 5 Firmware Versions[\s\S]{0,200}?(\d+\.\d+\.\d+)"),
]


def targets() -> list[Target]:
    return [
        Target(name=name, aliases=list(aliases), vendor=vendor, category=category, search_names=list(search_names))
        for name, aliases, vendor, category, search_names in _TARGETS
    ]


def version_checks() -> list[VendorConfig]:
    return [
        VendorConfig(vendor=name, target=name, url_template=url, fetch="http", selector=None, select=select, regex=regex)
        for name, url, select, regex in _CHECKS
    ]


def seed(target_repo, vendor_config_repo, version_repo=None) -> dict[str, int]:
    for target in targets():
        target_repo.upsert(target)
    for config in version_checks():
        vendor_config_repo.upsert(config)
    vendor_config_repo.delete("Samsung Galaxy S26")
    samsung = target_repo.find_by_name("Samsung Galaxy S26")
    if samsung is not None and version_repo is not None:
        version_repo.delete_by_target(samsung.storage_id)
    return {"targets": len(_TARGETS), "configs": len(_CHECKS)}
