from pathlib import Path

import pytest

from updater.application.firmware_lookup import _select_match
from updater.infrastructure.seed.version_checks import seed, targets, version_checks

FIXTURES = Path(__file__).parent.parent / "fixtures" / "version"

EXPECTED = {
    "Philips Hue Bridge Pro": ("philips.html", "2071401010"),
    "Samsung Galaxy S26": ("samsung.html", "Aug-2026 Release 1"),
    "Home Assistant Green": ("home_assistant.html", "18.2"),
    "OpenAI Codex": ("codex.html", "0.147.0"),
    "Anthropic Claude Code": ("claude_code.html", "2.1.233"),
    "Postgres pgvector": ("pgvector.html", "0.8.6"),
    "Oracle Autonomous AI Database": ("oracle.html", "23.26.3"),
    "LiteLLM": ("litellm.html", "v1.97.0"),
    "NVIDIA Dynamo": ("dynamo.html", "v1.4.0"),
    "Chroma": ("chroma.html", "1.5.9"),
}


@pytest.mark.parametrize("config", version_checks(), ids=lambda c: c.target)
def test_seed_regex_extracts_expected_version_from_fixture(config):
    fixture_name, expected = EXPECTED[config.target]
    html = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    match = _select_match(config.regex, html, config.select)
    assert match is not None, f"no match for {config.target}"
    assert match.group(1).strip() == expected


def test_seed_covers_all_ten_targets():
    assert len(version_checks()) == 10
    assert {t.name for t in targets()} == set(EXPECTED)


class _Repo:
    def __init__(self):
        self.items = []

    def upsert(self, item):
        self.items.append(item)
        return item


def test_seed_upserts_targets_and_configs():
    target_repo, config_repo = _Repo(), _Repo()
    counts = seed(target_repo, config_repo)
    assert counts == {"targets": 10, "configs": 10}
    assert len(target_repo.items) == 10
    assert len(config_repo.items) == 10
