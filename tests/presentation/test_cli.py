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
