from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import tasks

from updater.application.export_json import ExportService
from updater.application.sync_vulnerabilities import SyncVulnerabilitiesService
from updater.infrastructure.browser.cloak import CloakBrowserAdapter
from updater.infrastructure.mongo import (
    MongoDatabase,
    MongoTargetRepository,
    MongoTargetVersionRepository,
    MongoTargetVulnerabilityRepository,
    MongoVendorConfigRepository,
    MongoVulnerabilityRepository,
)
from updater.infrastructure.sources.nvd import NvdSource
from updater.infrastructure.sources.zdi import ZdiSource
from updater.presentation.discord_bot import commands as cmd
from updater.presentation.discord_bot.config import BotConfig, ConfigError, load_config
from updater.presentation.discord_bot.formatting import (
    build_finding_embed,
    build_summary_message,
    group_findings,
)
from updater.presentation.discord_bot.permissions import has_admin_role
from updater.presentation.discord_bot.scheduler import FireTracker


log = logging.getLogger("updater.bot")


_EMBEDS_PER_MESSAGE_LIMIT = 10
_EMBED_TOTAL_PER_MESSAGE_LIMIT = 6000


def _embed_size(embed: object) -> int:
    title = getattr(embed, "title", None) or ""
    description = getattr(embed, "description", None) or ""
    fields = getattr(embed, "fields", [])
    return len(title) + len(description) + sum(
        len(getattr(field, "name", "")) + len(getattr(field, "value", "")) for field in fields
    )


def _chunk_embeds(embeds: list[object], *, size: int = _EMBEDS_PER_MESSAGE_LIMIT) -> list[list[object]]:
    chunks: list[list[object]] = []
    current: list[object] = []
    current_size = 0
    for embed in embeds:
        embed_size = _embed_size(embed)
        if current and (len(current) >= size or current_size + embed_size > _EMBED_TOTAL_PER_MESSAGE_LIMIT):
            chunks.append(current)
            current = []
            current_size = 0
        current.append(embed)
        current_size += embed_size
    if current:
        chunks.append(current)
    return chunks


async def _send_command_result(send, result: cmd.CommandResult) -> None:
    if not result.embeds:
        await send(content=result.text)
        return
    chunks = _chunk_embeds(result.embeds, size=10)
    await send(
        content=f"{result.text} — showing 1-{len(chunks[0])} of {len(result.embeds)}",
        embeds=chunks[0],
    )
    shown = len(chunks[0])
    for chunk in chunks[1:]:
        start = shown + 1
        shown += len(chunk)
        await send(
            content=f"Showing {start}-{shown} of {len(result.embeds)}",
            embeds=chunk,
        )


def _local_to_utc(local_hour: int, local_minute: int, tz) -> tuple[int, int]:
    from datetime import datetime as _dt
    ref = _dt(2000, 1, 2, local_hour, local_minute, tzinfo=tz)
    utc_ref = ref.astimezone(timezone.utc)
    return utc_ref.hour, utc_ref.minute


async def _resolve_channel(client, channel_id: int):
    return client.get_channel(channel_id) or await client.fetch_channel(channel_id)


def build_client(config: BotConfig) -> discord.Client:
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = False
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)
    guild = discord.Object(id=config.guild_id)

    services = _build_services(config)
    tracker = FireTracker()

    async def _admin_only(interaction: discord.Interaction) -> bool:
        if not has_admin_role(interaction.user, admin_role_id=config.admin_role_id):
            await interaction.response.send_message(
                "Admin role required.", ephemeral=True
            )
            return False
        return True

    async def _reply(interaction: discord.Interaction, result: cmd.CommandResult, *, ephemeral=False):
        await interaction.response.send_message(
            content=result.text or None,
            embeds=result.embeds,
            ephemeral=ephemeral,
        )

    @tree.command(name="list-targets", description="List all targets", guild=guild)
    async def list_targets(interaction: discord.Interaction):
        await _reply(interaction, await cmd.handle_list_targets(services))

    @tree.command(name="show-target", description="Show target details", guild=guild)
    @app_commands.describe(
        target_id="Target number from /list-targets",
        limit="Optional number of recent vulnerabilities to show",
    )
    async def show_target(
        interaction: discord.Interaction,
        target_id: int,
        limit: int | None = None,
    ):
        await _reply(interaction, await cmd.handle_show_target(services, target_id=target_id, limit=limit))

    @tree.command(name="add-target", description="Add a target", guild=guild)
    @app_commands.describe(
        name="Target name",
        aliases="Semicolon-separated aliases",
        vendor="Vendor",
        vendor_alias="URL path segment for firmware lookup",
        category="Category",
    )
    async def add_target(
        interaction: discord.Interaction,
        name: str,
        aliases: str | None = None,
        vendor: str | None = None,
        vendor_alias: str | None = None,
        category: str | None = None,
    ):
        if not await _admin_only(interaction):
            return
        alias_list = [a.strip() for a in (aliases or "").split(";") if a.strip()]
        await _reply(
            interaction,
            await cmd.handle_add_target(
                services, name=name, aliases=alias_list, vendor=vendor, vendor_alias=vendor_alias, category=category
            ),
        )

    @tree.command(name="remove-target", description="Remove one or more targets", guild=guild)
    @app_commands.describe(names="Comma-separated target names")
    async def remove_target(interaction: discord.Interaction, names: str):
        if not await _admin_only(interaction):
            return
        name_list = [n.strip() for n in names.split(",") if n.strip()]
        await _reply(interaction, await cmd.handle_remove_target(services, names=name_list))

    @tree.command(name="import-targets", description="Import targets from a CSV file", guild=guild)
    async def import_targets(interaction: discord.Interaction, file: discord.Attachment):
        if not await _admin_only(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        data = await file.read()
        result = await cmd.handle_import_targets(services, csv_bytes=data)
        await interaction.followup.send(content=result.text, ephemeral=True)

    @tree.command(name="clear-database", description="Clear all stored targets and vulnerabilities", guild=guild)
    @app_commands.describe(confirm="Type DELETE to confirm clearing the database")
    async def clear_database(interaction: discord.Interaction, confirm: str):
        if not await _admin_only(interaction):
            return
        await _reply(interaction, await cmd.handle_clear_database(services, confirm=confirm), ephemeral=True)

    @tree.command(name="add-vuln", description="Manually add a vulnerability", guild=guild)
    @app_commands.describe(
        advisory_id="Advisory ID (e.g. CVE-2024-12647)",
        description="Description",
        cvss_score="CVSS score",
        severity="Severity (CRITICAL/HIGH/MEDIUM/LOW/INFORMATIONAL/NONE)",
        references="Comma-separated reference URLs",
        target_name="Optional target name to link",
    )
    async def add_vuln(
        interaction: discord.Interaction,
        advisory_id: str,
        description: str,
        cvss_score: float | None = None,
        severity: str | None = None,
        references: str | None = None,
        target_name: str | None = None,
    ):
        if not await _admin_only(interaction):
            return
        ref_list = [r.strip() for r in (references or "").split(",") if r.strip()]
        await _reply(
            interaction,
            await cmd.handle_add_vuln(
                services,
                advisory_id=advisory_id,
                description=description,
                cvss_score=cvss_score,
                severity=severity,
                references=ref_list,
                target_name=target_name,
            ),
        )

    @tree.command(name="set-vendor-firmware", description="Set vendor firmware lookup config", guild=guild)
    @app_commands.describe(
        vendor="Vendor name",
        url_template="HTTPS URL with {alias} placeholder",
        attr_id="HTML element ID to scrape",
        regex="Regex with 2+ groups (version, download URL)",
    )
    async def set_vendor_firmware(
        interaction: discord.Interaction,
        vendor: str,
        url_template: str,
        attr_id: str,
        regex: str,
    ):
        if not await _admin_only(interaction):
            return
        await _reply(
            interaction,
            await cmd.handle_set_vendor_firmware(
                services, vendor=vendor, url_template=url_template, attr_id=attr_id, regex=regex
            ),
        )

    @tree.command(name="set-vendor-alias", description="Set vendor alias for firmware lookup", guild=guild)
    @app_commands.describe(
        target_id="Target number from /list-targets",
        vendor_alias="URL path segment for vendor firmware page",
    )
    async def set_vendor_alias(
        interaction: discord.Interaction,
        target_id: int,
        vendor_alias: str,
    ):
        if not await _admin_only(interaction):
            return
        await _reply(
            interaction,
            await cmd.handle_set_vendor_alias(services, target_id=target_id, vendor_alias=vendor_alias),
        )

    @tree.command(name="lookup-firmware", description="Look up firmware version for a target", guild=guild)
    @app_commands.describe(
        target_id="Target number from /list-targets",
        url_template="Optional: override stored URL template",
        attr_id="Optional: override stored element ID",
        regex="Optional: override stored regex",
    )
    async def lookup_firmware(
        interaction: discord.Interaction,
        target_id: int,
        url_template: str | None = None,
        attr_id: str | None = None,
        regex: str | None = None,
    ):
        await _reply(
            interaction,
            await cmd.handle_lookup_firmware(
                services, target_id=target_id, url_template=url_template, attr_id=attr_id, regex=regex
            ),
        )

    @tree.command(name="import-vendor-firmware", description="Import vendor firmware configs from CSV", guild=guild)
    async def import_vendor_firmware(interaction: discord.Interaction, file: discord.Attachment):
        if not await _admin_only(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        data = await file.read()
        result = await cmd.handle_import_vendor_firmware(services, csv_bytes=data)
        await interaction.followup.send(content=result.text, ephemeral=True)

    @tree.command(name="sync-cves", description="Sync vulnerabilities now", guild=guild)
    @app_commands.describe(target="Optional target name; omit to sync all")
    async def sync_cves(interaction: discord.Interaction, target: str | None = None):
        if not await _admin_only(interaction):
            return
        channel = interaction.channel
        if channel is None:
            await interaction.response.send_message("Cannot run sync outside a channel.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Sync started. Results will be posted in this channel when complete.",
            ephemeral=True,
        )

        async def _run_manual_sync() -> None:
            try:
                result = await cmd.handle_sync_cves(services, target_name=target)
                await _send_command_result(channel.send, result)
            except Exception:
                log.exception("manual sync failed")
                await channel.send("Manual sync failed. Check bot logs for details.")

        asyncio.create_task(_run_manual_sync())

    @tree.command(name="search-vulns", description="Search stored vulnerabilities", guild=guild)
    @app_commands.describe(
        severity="Optional severity filter (CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL, NONE)",
        year="Optional year to match by advisory ID or published date",
        from_date="Optional collected start date (YYYY-MM-DD); defaults to today",
        to_date="Optional collected end date (YYYY-MM-DD); defaults to today",
    )
    async def search_vulns(
        interaction: discord.Interaction,
        severity: str | None = None,
        year: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ):
        result = await cmd.handle_search_vulns(
            services,
            severity=severity,
            year=year,
            from_date=from_date,
            to_date=to_date,
            today=datetime.now(config.tz).date(),
        )
        if result.ephemeral:
            await interaction.response.send_message(content=result.text, ephemeral=True)
            return
        await interaction.response.defer(thinking=True, ephemeral=False)
        if not result.embeds:
            await interaction.followup.send(content=result.text)
            return
        chunks = _chunk_embeds(result.embeds, size=10)
        await interaction.followup.send(
            content=f"{result.text} — showing 1-{len(chunks[0])} of {len(result.embeds)}",
            embeds=chunks[0],
        )
        shown = len(chunks[0])
        for chunk in chunks[1:]:
            start = shown + 1
            shown += len(chunk)
            await interaction.followup.send(
                content=f"Showing {start}-{shown} of {len(result.embeds)}",
                embeds=chunk,
            )

    @tree.command(name="set-schedule", description="Set daily sync and notify times", guild=guild)
    @app_commands.describe(sync_time="HH:MM", notify_time="HH:MM")
    async def set_schedule(interaction: discord.Interaction, sync_time: str, notify_time: str):
        if not await _admin_only(interaction):
            return
        result = await cmd.handle_set_schedule(
            env_path=config.env_path,
            sync_time=sync_time,
            notify_time=notify_time,
        )
        await _reply(interaction, result)

    @tree.command(name="show-schedule", description="Show current schedule", guild=guild)
    async def show_schedule(interaction: discord.Interaction):
        current = _reload_or_keep(config)
        await _reply(
            interaction,
            await cmd.handle_show_schedule(
                sync_time=current.sync_time, notify_time=current.notify_time
            ),
        )

    @client.event
    async def on_ready():
        await tree.sync(guild=guild)
        log.info("Bot ready. Commands synced to guild %s.", config.guild_id)
        if not _scheduler_loop.is_running():
            _scheduler_loop.start()

    @tasks.loop(seconds=60)
    async def _scheduler_loop():
        try:
            current = _reload_or_keep(config)
            events = tracker.check(
                now=datetime.now(timezone.utc),
                sync_time=_local_to_utc(*current.sync_time, current.tz),
                notify_time=_local_to_utc(*current.notify_time, current.tz),
            )
            for event in events:
                if event == "sync":
                    await _run_sync(services)
                elif event == "notify":
                    try:
                        channel = await _resolve_channel(client, config.channel_id)
                    except discord.NotFound:
                        log.warning("notify channel %s does not exist (404), skipping tick", config.channel_id)
                        continue
                    except discord.Forbidden:
                        log.warning("notify channel %s access denied (403), bot lacks permissions, skipping tick", config.channel_id)
                        continue
                    except discord.HTTPException as exc:
                        log.warning("notify channel %s fetch failed (status=%s text=%s), skipping tick", config.channel_id, exc.status, exc.text)
                        continue
                    await _run_notify(services, channel, current.tz)
        except Exception:
            log.exception("scheduler tick failed")

    return client


def _reload_or_keep(default_config: BotConfig) -> BotConfig:
    try:
        return load_config(default_config.env_path)
    except ConfigError:
        return default_config


def _build_services(config: BotConfig) -> cmd.Services:
    db = MongoDatabase(uri=config.mongodb_uri, database=config.mongodb_database)
    return cmd.Services(
        target_repo=MongoTargetRepository(db.db),
        version_repo=MongoTargetVersionRepository(db.db),
        vulnerability_repo=MongoVulnerabilityRepository(db.db),
        target_vulnerability_repo=MongoTargetVulnerabilityRepository(db.db),
        sources=[NvdSource(), ZdiSource()],
        vendor_config_repo=MongoVendorConfigRepository(db.db),
        browser=CloakBrowserAdapter(),
    )


async def _run_sync(services: cmd.Services) -> None:
    log.info("scheduled sync starting")
    try:
        result = await asyncio.to_thread(
            SyncVulnerabilitiesService(
                services.target_repo,
                services.vulnerability_repo,
                services.target_vulnerability_repo,
                services.sources,
            ).sync_all
        )
        log.info(
            "scheduled sync done targets=%d vulns=%d errors=%d",
            result.targets_processed,
            result.vulnerabilities_seen,
            len(result.errors),
        )
    except Exception:
        log.exception("scheduled sync failed")


async def _run_notify(services: cmd.Services, channel, tz) -> None:
    log.info("scheduled notify starting")
    try:
        snapshot = await asyncio.to_thread(
            ExportService(
                services.target_repo,
                services.vulnerability_repo,
                services.target_vulnerability_repo,
            ).snapshot
        )
    except Exception:
        log.exception("scheduled notify failed (snapshot)")
        return

    findings = group_findings(snapshot)
    summary = build_summary_message(
        report_date=datetime.now(tz).date(),
        targets_processed=len(services.target_repo.list_all()),
        new_findings=len(findings),
        errors=0,
    )
    try:
        await channel.send(content=summary)
    except Exception:
        log.exception("scheduled notify: summary send failed")
        return
    for finding in findings:
        try:
            await channel.send(embed=build_finding_embed(finding))
        except Exception:
            log.exception("scheduled notify: finding send failed advisory=%s", finding.get("advisory_id"))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    env_path = Path(argv[0] if argv else ".env")
    try:
        config = load_config(env_path)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    client = build_client(config)
    client.run(config.discord_token, log_handler=None)
    return 0
