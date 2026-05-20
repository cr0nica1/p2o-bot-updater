import pytest

from updater.presentation.discord_bot.config import (
    BotConfig,
    ConfigError,
    load_config,
    parse_time,
    update_schedule,
)


def test_parse_time_accepts_hh_mm():
    assert parse_time("08:00") == (8, 0)
    assert parse_time("23:59") == (23, 59)
    assert parse_time(" 9:05 ") == (9, 5)


def test_parse_time_rejects_invalid():
    with pytest.raises(ConfigError):
        parse_time("24:00")
    with pytest.raises(ConfigError):
        parse_time("8")
    with pytest.raises(ConfigError):
        parse_time("abc")
    with pytest.raises(ConfigError):
        parse_time("12:60")


def test_load_config_reads_all_fields(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=tok\n"
        "DISCORD_GUILD_ID=111\n"
        "DISCORD_CHANNEL_ID=222\n"
        "DISCORD_ADMIN_ROLE_ID=333\n"
        "SYNC_TIME=08:00\n"
        "NOTIFY_TIME=09:30\n"
        "MONGODB_URI=mongodb://localhost:27017\n"
        "MONGODB_DATABASE=pwn2own_updater\n"
    )

    config = load_config(env_file)

    assert config == BotConfig(
        env_path=env_file,
        discord_token="tok",
        guild_id=111,
        channel_id=222,
        admin_role_id=333,
        sync_time=(8, 0),
        notify_time=(9, 30),
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="pwn2own_updater",
    )


def test_load_config_missing_token_raises(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_GUILD_ID=111\n")
    with pytest.raises(ConfigError, match="DISCORD_TOKEN"):
        load_config(env_file)


def test_load_config_bad_time_raises(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=tok\n"
        "DISCORD_GUILD_ID=111\n"
        "DISCORD_CHANNEL_ID=222\n"
        "DISCORD_ADMIN_ROLE_ID=333\n"
        "SYNC_TIME=2500\n"
        "NOTIFY_TIME=09:30\n"
    )
    with pytest.raises(ConfigError, match="SYNC_TIME"):
        load_config(env_file)


def test_update_schedule_rewrites_existing_lines(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=tok\n"
        "SYNC_TIME=08:00\n"
        "NOTIFY_TIME=09:00\n"
    )

    update_schedule(env_file, sync_time="10:15", notify_time="11:30")

    text = env_file.read_text()
    assert "SYNC_TIME=10:15" in text
    assert "NOTIFY_TIME=11:30" in text
    assert "DISCORD_TOKEN=tok" in text
    assert text.count("SYNC_TIME=") == 1
    assert text.count("NOTIFY_TIME=") == 1


def test_update_schedule_appends_when_missing(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=tok\n")

    update_schedule(env_file, sync_time="10:15", notify_time="11:30")

    text = env_file.read_text()
    assert "SYNC_TIME=10:15" in text
    assert "NOTIFY_TIME=11:30" in text


def test_update_schedule_validates_format(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=tok\n")
    with pytest.raises(ConfigError):
        update_schedule(env_file, sync_time="bad", notify_time="11:30")
