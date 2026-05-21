from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import dotenv_values


class ConfigError(Exception):
    pass


UTC_PLUS_7 = timezone(timedelta(hours=7))


def _parse_tz(value: str | None) -> timezone:
    mapping = {
        "UTC+7": UTC_PLUS_7,
        "UTC-7": timezone(timedelta(hours=-7)),
    }
    if value is None:
        return UTC_PLUS_7
    key = value.strip().upper()
    if key in mapping:
        return mapping[key]
    import re
    m = re.match(r"^UTC([+-])(\d{1,2})(?::?(\d{2}))?$", key)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        hours = int(m.group(2))
        minutes = int(m.group(3) or 0)
        return timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
    raise ConfigError(f"unsupported timezone format: {value!r}, use UTC+7 or UTC-5:30")


@dataclass(frozen=True)
class BotConfig:
    env_path: Path
    discord_token: str
    guild_id: int
    channel_id: int
    admin_role_id: int
    sync_time: tuple[int, int]
    notify_time: tuple[int, int]
    mongodb_uri: str
    mongodb_database: str
    tz: timezone = UTC_PLUS_7


_REQUIRED_STR = ("DISCORD_TOKEN",)
_REQUIRED_INT = ("DISCORD_GUILD_ID", "DISCORD_CHANNEL_ID", "DISCORD_ADMIN_ROLE_ID")
_REQUIRED_TIME = ("SYNC_TIME", "NOTIFY_TIME")


def parse_time(value: str) -> tuple[int, int]:
    if not isinstance(value, str):
        raise ConfigError(f"time must be a string, got {value!r}")
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ConfigError(f"time must be HH:MM, got {value!r}")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ConfigError(f"time must be HH:MM, got {value!r}") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ConfigError(f"time out of range, got {value!r}")
    return hour, minute


def load_config(env_path: Path) -> BotConfig:
    if not env_path.exists():
        raise ConfigError(f".env file not found: {env_path}")
    values = dotenv_values(env_path)

    def _require(key: str) -> str:
        raw = values.get(key)
        if raw is None or raw.strip() == "":
            raise ConfigError(f"{key} is required in {env_path}")
        return raw.strip()

    for key in _REQUIRED_STR + _REQUIRED_INT + _REQUIRED_TIME:
        _require(key)

    int_fields: dict[str, int] = {}
    for key in _REQUIRED_INT:
        raw = _require(key)
        try:
            int_fields[key] = int(raw)
        except ValueError as exc:
            raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc

    time_fields: dict[str, tuple[int, int]] = {}
    for key in _REQUIRED_TIME:
        try:
            time_fields[key] = parse_time(_require(key))
        except ConfigError as exc:
            raise ConfigError(f"{key}: {exc}") from exc

    return BotConfig(
        env_path=env_path,
        discord_token=_require("DISCORD_TOKEN"),
        guild_id=int_fields["DISCORD_GUILD_ID"],
        channel_id=int_fields["DISCORD_CHANNEL_ID"],
        admin_role_id=int_fields["DISCORD_ADMIN_ROLE_ID"],
        sync_time=time_fields["SYNC_TIME"],
        notify_time=time_fields["NOTIFY_TIME"],
        mongodb_uri=(values.get("MONGODB_URI") or "mongodb://localhost:27017").strip(),
        mongodb_database=(values.get("MONGODB_DATABASE") or "pwn2own_updater").strip(),
        tz=_parse_tz(values.get("TIMEZONE")),
    )


def update_schedule(env_path: Path, *, sync_time: str, notify_time: str) -> None:
    parse_time(sync_time)
    parse_time(notify_time)

    lines = env_path.read_text().splitlines() if env_path.exists() else []
    updates = {"SYNC_TIME": sync_time, "NOTIFY_TIME": notify_time}

    seen: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if "=" not in stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            if key in seen:
                continue  # drop duplicate occurrence
            new_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            new_lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines) + "\n")
