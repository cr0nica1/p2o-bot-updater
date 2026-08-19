from pathlib import Path

import pytest

from updater.application.firmware_lookup import _select_match
from updater.infrastructure.seed.version_checks import seed, targets, version_checks

FIXTURES = Path(__file__).parent.parent / "fixtures" / "version"

EXPECTED = {
    "Philips Hue Bridge Pro": ("philips.html", "2071401010"),
    "Home Assistant Green": ("home_assistant.html", "18.2"),
    "OpenAI Codex": ("codex.html", "0.147.0"),
    "Anthropic Claude Code": ("claude_code.html", "2.1.233"),
    "Postgres pgvector": ("pgvector.html", "0.8.6"),
    "Oracle Autonomous AI Database": ("oracle.html", "23.26.3"),
    "LiteLLM": ("litellm.html", "v1.97.0"),
    "NVIDIA Dynamo": ("dynamo.html", "v1.4.0"),
    "Chroma": ("chroma.html", "1.5.9"),
    "Oura Ring 5": ("oura.html", "2.1.3"),
}

TARGET_NAMES = {
    *EXPECTED,
    "Samsung Galaxy S26",
}


@pytest.mark.parametrize("config", version_checks(), ids=lambda c: c.target)
def test_seed_regex_extracts_expected_version_from_fixture(config):
    fixture_name, expected = EXPECTED[config.target]
    html = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    match = _select_match(config.regex, html, config.select)
    assert match is not None, f"no match for {config.target}"
    assert match.group(1).strip() == expected


def test_seed_covers_eleven_targets_and_ten_checkers():
    assert len(version_checks()) == 10
    assert {t.name for t in targets()} == TARGET_NAMES
    assert "Samsung Galaxy S26" not in {c.target for c in version_checks()}


def test_chroma_search_names_are_chromadb_only():
    chroma = next(t for t in targets() if t.name == "Chroma")
    assert chroma.search_queries() == ["ChromaDB"]


def test_claude_and_pgvector_aliases():
    by_name = {t.name: t for t in targets()}
    assert "Claude Code" in by_name["Anthropic Claude Code"].search_queries()
    assert "pgvector" in by_name["Postgres pgvector"].search_queries()
    assert "Philips Hue Bridge" in by_name["Philips Hue Bridge Pro"].search_queries()


def test_pgvector_checker_uses_raw_github():
    config = next(c for c in version_checks() if c.target == "Postgres pgvector")
    assert "raw.githubusercontent.com" in config.url_template


class _Repo:
    def __init__(self):
        self.items = []

    def upsert(self, item):
        self.items.append(item)
        return item

    def find_by_name(self, name):
        return next((i for i in self.items if getattr(i, "name", None) == name), None)

    def delete(self, vendor):
        before = len(self.items)
        self.items = [i for i in self.items if getattr(i, "vendor", None) != vendor]
        return before != len(self.items)

    def delete_by_target(self, target_id):
        return 0


def test_seed_upserts_targets_and_configs():
    target_repo, config_repo = _Repo(), _Repo()
    counts = seed(target_repo, config_repo)
    assert counts == {"targets": 11, "configs": 10}
    assert len(target_repo.items) == 11
    assert len(config_repo.items) == 10
