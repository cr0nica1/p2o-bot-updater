from __future__ import annotations

import argparse
import sys
from pathlib import Path

from updater.application.firmware_lookup import FirmwareLookupError, validate_vendor_config
from updater.domain.models import VendorConfig
from updater.infrastructure.mongo import MongoDatabase, MongoVendorConfigRepository
from updater.presentation.discord_bot.config import ConfigError, load_config


def _build_repo(env_path: Path):
    config = load_config(env_path)
    db = MongoDatabase(uri=config.mongodb_uri, database=config.mongodb_database)
    return MongoVendorConfigRepository(db.db)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vendor-config")
    parser.add_argument("--env", default=".env", help="Path to .env file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add")
    add.add_argument("--vendor", required=True)
    add.add_argument("--url-template", required=True)
    add.add_argument("--attr-id", default="")
    add.add_argument("--regex", required=True)
    add.add_argument("--target")
    add.add_argument("--fetch", default="browser", choices=["browser", "http"])
    add.add_argument("--selector")
    add.add_argument("--select", default="first", choices=["first", "last", "max"])

    subparsers.add_parser("list")

    remove = subparsers.add_parser("remove")
    remove.add_argument("--vendor", required=True)

    subparsers.add_parser("seed")
    return parser


def main(argv: list[str] | None = None, *, repo=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        repository = repo or _build_repo(Path(args.env))
        if args.command == "add":
            config = VendorConfig(
                vendor=args.vendor,
                url_template=args.url_template,
                attr_id=args.attr_id,
                regex=args.regex,
                target=args.target,
                fetch=args.fetch,
                selector=args.selector,
                select=args.select,
            )
            validate_vendor_config(config)
            repository.upsert(config)
            print(f"Saved vendor config: {args.vendor}")
            return 0
        if args.command == "list":
            configs = repository.list_all()
            if not configs:
                print("No vendor configs.")
                return 0
            for config in configs:
                print(f"{config.vendor}: attr_id={config.attr_id} url_template={config.url_template}")
            return 0
        if args.command == "remove":
            if repository.delete(args.vendor):
                print(f"Removed vendor config: {args.vendor}")
                return 0
            print(f"Vendor config not found: {args.vendor}", file=sys.stderr)
            return 1
        if args.command == "seed":
            from updater.infrastructure.mongo import MongoDatabase, MongoTargetRepository
            from updater.infrastructure.seed.version_checks import seed as seed_version_checks

            config = load_config(Path(args.env))
            db = MongoDatabase(uri=config.mongodb_uri, database=config.mongodb_database)
            counts = seed_version_checks(
                MongoTargetRepository(db.db), MongoVendorConfigRepository(db.db)
            )
            print(f"Seeded {counts['targets']} targets and {counts['configs']} version checks.")
            return 0
    except (ConfigError, FirmwareLookupError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
