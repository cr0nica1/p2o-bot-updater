from __future__ import annotations

from datetime import datetime


class FireTracker:
    """Pure state machine deciding whether sync/notify should fire on this tick.

    Each event fires at most once per (date, configured_time) pair. Changing the
    configured time on the same day re-arms the corresponding event.
    """

    def __init__(self) -> None:
        self._last_fired: dict[str, tuple[str, tuple[int, int]]] = {}

    def check(
        self,
        *,
        now: datetime,
        sync_time: tuple[int, int],
        notify_time: tuple[int, int],
    ) -> tuple[str, ...]:
        fired: list[str] = []
        for event, configured in (("sync", sync_time), ("notify", notify_time)):
            if self._should_fire(event, now, configured):
                self._last_fired[event] = (now.date().isoformat(), configured)
                fired.append(event)
        return tuple(fired)

    def _should_fire(
        self, event: str, now: datetime, configured: tuple[int, int]
    ) -> bool:
        hour, minute = configured
        if (now.hour, now.minute) < (hour, minute):
            return False
        previous = self._last_fired.get(event)
        if previous is None:
            return True
        prev_date, prev_configured = previous
        return prev_date != now.date().isoformat() or prev_configured != configured
