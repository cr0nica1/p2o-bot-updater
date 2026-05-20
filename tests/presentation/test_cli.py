from updater.presentation.cli import build_parser


def test_parser_accepts_sync_targets():
    args = build_parser().parse_args(["sync", "--targets", "targets.csv"])

    assert args.command == "sync"
    assert args.targets == "targets.csv"


def test_parser_accepts_sync_cves_target_filter():
    args = build_parser().parse_args(["sync-cves", "--target", "Adobe Reader"])

    assert args.command == "sync-cves"
    assert args.target == "Adobe Reader"


def test_parser_accepts_export_json_output():
    args = build_parser().parse_args(["export-json", "--out", "output.json"])

    assert args.command == "export-json"
    assert args.out == "output.json"


def test_parser_accepts_clear_data_with_yes():
    args = build_parser().parse_args(["clear-data", "--yes"])

    assert args.command == "clear-data"
    assert args.yes is True


def test_parser_rejects_clear_data_without_yes():
    args = build_parser().parse_args(["clear-data"])

    assert args.command == "clear-data"
    assert args.yes is False


def test_parser_accepts_clear_targets_with_yes():
    args = build_parser().parse_args(["clear-targets", "--yes"])

    assert args.command == "clear-targets"
    assert args.yes is True
