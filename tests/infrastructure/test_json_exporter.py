import json
from pathlib import Path

from updater.infrastructure.json_exporter import JsonExporter


def test_json_exporter_writes_pretty_json(tmp_path: Path):
    output = tmp_path / "output.json"

    JsonExporter().write(output, {"targets": [{"name": "Adobe Reader"}]})

    assert json.loads(output.read_text(encoding="utf-8")) == {"targets": [{"name": "Adobe Reader"}]}
    assert output.read_text(encoding="utf-8").startswith("{\n  ")
