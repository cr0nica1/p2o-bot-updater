from datetime import date

from updater.application.version_scan import version_changes_from_docs
from updater.domain.models import Target, TargetVersion
from updater.presentation.discord_bot.formatting import build_version_update_message


def test_notify_pipeline_builds_message_for_recent_changes():
    targets = [Target(name="Chroma", id="c1")]
    docs = [TargetVersion(target_id="c1", version="1.6.0", previous_version="1.5.9", source_url="u")]
    changes = version_changes_from_docs(docs, targets)
    assert changes  # non-empty → the bot posts a version section
    msg = build_version_update_message(report_date=date(2026, 8, 18), changes=changes)
    assert "• Chroma: 1.5.9 → 1.6.0" in msg


def test_notify_pipeline_is_empty_when_no_recent_changes():
    targets = [Target(name="Chroma", id="c1")]
    changes = version_changes_from_docs([], targets)
    assert changes == []  # empty → the bot posts no version section
