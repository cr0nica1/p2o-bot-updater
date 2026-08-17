from __future__ import annotations

from updater.domain.models import Target, VendorConfig

# (name, category, url, select, regex) — every checker uses http fetch and no selector.
_CHECKS = [
    ("Philips Hue Bridge Pro", "Smart Home",
     "https://www.philips-hue.com/en-us/support/release-notes/bridge-pro",
     "first", r"Software version\s+(\d{10})"),
    ("Samsung Galaxy S26", "Mobile Phone",
     "https://security.samsungmobile.com/securityUpdate.smsb",
     "first",
     r"(?i)SMR[ -]((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-20\d{2}\s+Release\s+\d+)"),
    ("Home Assistant Green", "Smart Home",
     "https://github.com/home-assistant/operating-system/releases",
     "first", r'releases/tag/(\d+\.\d+(?:\.\d+)?)"'),
    ("OpenAI Codex", "Coding Agent",
     "https://learn.chatgpt.com/docs/changelog?type=codex-cli",
     "first", r"@openai/codex@(\d+\.\d+\.\d+)"),
    ("Anthropic Claude Code", "Coding Agent",
     "https://code.claude.com/docs/en/changelog",
     "first", r'data-component-part="update-label"[^>]*>\s*(\d+\.\d+\.\d+)'),
    ("Postgres pgvector", "AI infrastructure",
     "https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md",
     "first", r"##\s+(\d+\.\d+\.\d+)\s+\(\d{4}-\d{2}-\d{2}\)"),
    ("Oracle Autonomous AI Database", "AI infrastructure",
     "https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/autonomous-ai-database-updates.html",
     "max", r"(?:Release Update\s+|release-update-)(\d+(?:\.\d+){1,2})"),
    ("LiteLLM", "AI infrastructure",
     "https://docs.litellm.ai/release_notes/",
     "first", r'id="?latest-release"?[\s\S]*?/release_notes/(v\d+\.\d+\.\d+)/'),
    ("NVIDIA Dynamo", "AI infrastructure",
     "https://docs.nvidia.com/dynamo/reference/releases",
     "first", r"Latest\s*\((v\d+\.\d+\.\d+)\)"),
    ("Chroma", "AI infrastructure",
     "https://github.com/chroma-core/chroma/releases",
     "first", r'releases/tag/(\d+\.\d+\.\d+)(?=["/#?])'),
]


def targets() -> list[Target]:
    return [Target(name=name, category=category) for name, category, *_ in _CHECKS]


def version_checks() -> list[VendorConfig]:
    return [
        VendorConfig(
            vendor=name,
            target=name,
            url_template=url,
            fetch="http",
            selector=None,
            select=select,
            regex=regex,
        )
        for name, _category, url, select, regex in _CHECKS
    ]


def seed(target_repo, vendor_config_repo) -> dict[str, int]:
    for target in targets():
        target_repo.upsert(target)
    for config in version_checks():
        vendor_config_repo.upsert(config)
    return {"targets": len(_CHECKS), "configs": len(_CHECKS)}
