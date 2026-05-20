from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import tasks

from updater.application.export_json import ExportService
from updater.application.sync_vulnerabilities import SyncVulnerabilitiesService
from updater.infrastructure.mongo import (
    MongoDatabase,
    MongoTargetRepository,
    MongoTargetVersionRepository,
    MongoTargetVulnerabilityRepository,
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
    @app_commands.describe(name="Target name")
    async def show_target(interaction: discord.Interaction, name: str):
        await _reply(interaction, await cmd.handle_show_target(services, name=name))

    @tree.command(name="add-target", description="Add a target", guild=guild)
    @app_commands.describe(
        name="Target name",
        aliases="Semicolon-separated aliases",
        vendor="Vendor",
        category="Category",
    )
    async def add_target(
        interaction: discord.Interaction,
        name: str,
        aliases: str | None = None,
        vendor: str | None = None,
        category: str | None = None,
    ):
        if not await _admin_only(interaction):
            return
        alias_list = [a.strip() for a in (aliases or "").split(";") if a.strip()]
        await _reply(
            interaction,
            await cmd.handle_add_target(
                services, name=name, aliases=alias_list, vendor=vendor, category=category
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

    @tree.command(name="sync-cves", description="Sync vulnerabilities now", guild=guild)
    @app_commands.describe(target="Optional target name; omit to sync all")
    async def sync_cves(interaction: discord.Interaction, target: str | None = None):
        if not await _admin_only(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        result = await cmd.handle_sync_cves(services, target_name=target)
        await interaction.followup.send(
            content=result.text or None, embeds=result.embeds, ephemeral=True
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
                sync_time=current.sync_time,
                notify_time=current.notify_time,
            )
            channel = client.get_channel(config.channel_id)
            for event in events:
                if event == "sync":
                    await _run_sync(services)
                elif event == "notify":
                    if channel is None:
                        log.warning("notify channel %s not found, skipping tick", config.channel_id)
                    else:
                        await _run_notify(services, channel)
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
    )


async def _run_sync(services: cmd.Services) -> None:
    log.info("scheduled sync starting")
    try:
        result = SyncVulnerabilitiesService(
            services.target_repo,
            services.vulnerability_repo,
            services.target_vulnerability_repo,
            services.sources,
        ).sync_all()
        log.info(
            "scheduled sync done targets=%d vulns=%d errors=%d",
            result.targets_processed,
            result.vulnerabilities_seen,
            len(result.errors),
        )
    except Exception:
        log.exception("scheduled sync failed")


async def _run_notify(services: cmd.Services, channel) -> None:
    log.info("scheduled notify starting")
    try:
        snapshot = ExportService(
            services.target_repo,
            services.vulnerability_repo,
            services.target_vulnerability_repo,
        ).snapshot()
    except Exception:
        log.exception("scheduled notify failed (snapshot)")
        return

    findings = group_findings(snapshot)
    summary = build_summary_message(
        report_date=datetime.now(timezone.utc).date(),
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
