from __future__ import annotations

import argparse
import sys
from pathlib import Path

from updater.application.firmware_lookup import FirmwareLookupError, FirmwareLookupService
from updater.infrastructure.browser import BrowserLaunchError, CloakBrowserAdapter
from updater.infrastructure.mongo import MongoDatabase, MongoTargetRepository, MongoVendorConfigRepository
from updater.presentation.discord_bot.config import ConfigError, load_config


def _build_service(env_path: Path) -> FirmwareLookupService:
    config = load_config(env_path)
    db = MongoDatabase(uri=config.mongodb_uri, database=config.mongodb_database)
    return FirmwareLookupService(
        target_repo=MongoTargetRepository(db.db),
        vendor_config_repo=MongoVendorConfigRepository(db.db),
        browser=CloakBrowserAdapter(),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="firmware-lookup")
    parser.add_argument("--env", default=".env", help="Path to .env file")
    parser.add_argument("--target-id", required=True, type=int, help="Target number from /list-targets")
    parser.add_argument("--url-template", help="HTTPS URL template containing {alias}")
    parser.add_argument("--attr-id", help="HTML element ID whose inner HTML will be searched")
    parser.add_argument("--regex", help="Regex with group 1 as version and group 2 as download URL")
    return parser


def main(argv: list[str] | None = None, *, service=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        lookup_service = service or _build_service(Path(args.env))
        runtime_values = [args.url_template, args.attr_id, args.regex]
        if any(value is not None for value in runtime_values):
            if not all(runtime_values):
                raise FirmwareLookupError("--url-template, --attr-id, and --regex must be provided together")
            result = lookup_service.lookup_with_inputs(
                target_id=args.target_id,
                url_template=args.url_template,
                attr_id=args.attr_id,
                regex=args.regex,
            )
        else:
            result = lookup_service.lookup(args.target_id)
    except (ConfigError, FirmwareLookupError, BrowserLaunchError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"Target: {result.target_name}")
    print(f"Vendor: {result.vendor}")
    print(f"Resolved URL: {result.resolved_url}")
    print(f"Firmware Version: {result.version}")
    print(f"Download URL: {result.download_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
