from __future__ import annotations

import os
from argparse import ArgumentParser, Namespace
from pathlib import Path

from updater.application.export_json import ExportService
from updater.application.import_targets import ImportTargetsService
from updater.application.sync_vulnerabilities import SyncVulnerabilitiesService
from updater.infrastructure.csv_loader import CsvTargetLoader
from updater.infrastructure.json_exporter import JsonExporter
from updater.infrastructure.mongo import (
    MongoDatabase,
    MongoTargetRepository,
    MongoTargetVersionRepository,
    MongoTargetVulnerabilityRepository,
    MongoVulnerabilityRepository,
)
from updater.infrastructure.sources.nvd import NvdSource
from updater.infrastructure.sources.zdi import ZdiSource


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="updater")
    parser.add_argument("--mongo-uri", default=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
    parser.add_argument("--mongo-db", default=os.environ.get("MONGODB_DATABASE", "pwn2own_updater"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync")
    sync_parser.add_argument("--targets", required=True)

    import_targets_parser = subparsers.add_parser("import-targets")
    import_targets_parser.add_argument("--targets", required=True)

    sync_cves_parser = subparsers.add_parser("sync-cves")
    sync_cves_parser.add_argument("--target")

    subparsers.add_parser("list-targets")

    export_json_parser = subparsers.add_parser("export-json")
    export_json_parser.add_argument("--out", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_command(args)


def run_command(args: Namespace) -> int:
    database = MongoDatabase(args.mongo_uri, args.mongo_db)
    database.ensure_indexes()
    target_repo = MongoTargetRepository(database.db)
    version_repo = MongoTargetVersionRepository(database.db)
    vulnerability_repo = MongoVulnerabilityRepository(database.db)
    target_vulnerability_repo = MongoTargetVulnerabilityRepository(database.db)

    if args.command == "import-targets":
        load_result = CsvTargetLoader().load(Path(args.targets))
        import_result = ImportTargetsService(target_repo, version_repo).import_items(
            [(item.target, item.version) for item in load_result.items]
        )
        print(
            f"targets_imported={import_result.targets_imported} "
            f"versions_imported={import_result.versions_imported} "
            f"errors={len(load_result.errors)}"
        )
        for error in load_result.errors:
            print(error)
        return 0 if not load_result.errors else 1

    if args.command == "sync":
        load_result = CsvTargetLoader().load(Path(args.targets))
        import_result = ImportTargetsService(target_repo, version_repo).import_items(
            [(item.target, item.version) for item in load_result.items]
        )
        sync_result = SyncVulnerabilitiesService(
            target_repo,
            vulnerability_repo,
            target_vulnerability_repo,
            [NvdSource(), ZdiSource()],
        ).sync_all()
        errors = [*load_result.errors, *sync_result.errors]
        print(
            f"targets_imported={import_result.targets_imported} "
            f"versions_imported={import_result.versions_imported} "
            f"targets_processed={sync_result.targets_processed} "
            f"vulnerabilities_seen={sync_result.vulnerabilities_seen} "
            f"links_updated={sync_result.links_updated} "
            f"errors={len(errors)}"
        )
        for error in errors:
            print(error)
        return 0 if not errors else 1

    if args.command == "sync-cves":
        service = SyncVulnerabilitiesService(
            target_repo,
            vulnerability_repo,
            target_vulnerability_repo,
            [NvdSource(), ZdiSource()],
        )
        sync_result = service.sync_one(args.target) if args.target else service.sync_all()
        print(
            f"targets_processed={sync_result.targets_processed} "
            f"vulnerabilities_seen={sync_result.vulnerabilities_seen} "
            f"links_updated={sync_result.links_updated} "
            f"errors={len(sync_result.errors)}"
        )
        for error in sync_result.errors:
            print(error)
        return 0 if not sync_result.errors else 1

    if args.command == "list-targets":
        for target in target_repo.list_all():
            print(target.name)
        return 0

    if args.command == "export-json":
        snapshot = ExportService(target_repo, vulnerability_repo, target_vulnerability_repo).snapshot()
        JsonExporter().write(Path(args.out), snapshot)
        print(f"exported={args.out}")
        return 0

    print(f"unsupported command: {args.command}")
    return 2
