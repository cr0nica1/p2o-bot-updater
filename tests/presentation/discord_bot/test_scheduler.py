from datetime import datetime, timezone

from updater.presentation.discord_bot.scheduler import FireTracker


def _at(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def test_fires_when_current_time_passes_configured_time():
    tracker = FireTracker()
    result = tracker.check(
        now=_at(2026, 5, 20, 8, 0),
        sync_time=(8, 0),
        notify_time=(9, 0),
    )
    assert result == ("sync",)


def test_does_not_fire_before_configured_time():
    tracker = FireTracker()
    result = tracker.check(
        now=_at(2026, 5, 20, 7, 59),
        sync_time=(8, 0),
        notify_time=(9, 0),
    )
    assert result == ()


def test_fires_each_event_once_per_day():
    tracker = FireTracker()
    tracker.check(now=_at(2026, 5, 20, 8, 0), sync_time=(8, 0), notify_time=(9, 0))
    result = tracker.check(now=_at(2026, 5, 20, 8, 1), sync_time=(8, 0), notify_time=(9, 0))
    assert result == ()


def test_fires_sync_and_notify_on_next_day():
    tracker = FireTracker()
    tracker.check(now=_at(2026, 5, 20, 8, 0), sync_time=(8, 0), notify_time=(9, 0))
    tracker.check(now=_at(2026, 5, 20, 9, 0), sync_time=(8, 0), notify_time=(9, 0))
    result_next_day_sync = tracker.check(
        now=_at(2026, 5, 21, 8, 0), sync_time=(8, 0), notify_time=(9, 0)
    )
    assert result_next_day_sync == ("sync",)
    result_next_day_notify = tracker.check(
        now=_at(2026, 5, 21, 9, 0), sync_time=(8, 0), notify_time=(9, 0)
    )
    assert result_next_day_notify == ("notify",)


def test_late_check_still_fires_once():
    """If the bot starts at 10:00 with sync_time=08:00, sync should still fire."""
    tracker = FireTracker()
    result = tracker.check(
        now=_at(2026, 5, 20, 10, 0),
        sync_time=(8, 0),
        notify_time=(9, 0),
    )
    assert set(result) == {"sync", "notify"}


def test_schedule_change_takes_effect():
    tracker = FireTracker()
    tracker.check(now=_at(2026, 5, 20, 8, 0), sync_time=(8, 0), notify_time=(9, 0))
    # change schedule, sync fires again same day at the new time
    result = tracker.check(
        now=_at(2026, 5, 20, 11, 0),
        sync_time=(11, 0),
        notify_time=(12, 0),
    )
    assert result == ("sync",)
