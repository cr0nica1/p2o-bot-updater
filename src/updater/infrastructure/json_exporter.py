from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonExporter:
    def write(self, path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
