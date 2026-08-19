from pathlib import Path

from updater.infrastructure.csv_loader import CsvTargetLoader


def test_loads_name_only_csv(tmp_path: Path):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text("name\nAdobe Acrobat Reader\n", encoding="utf-8")

    rows = CsvTargetLoader().load(csv_path)

    assert rows.errors == []
    assert rows.items[0].target.name == "Adobe Acrobat Reader"
    assert rows.items[0].target.aliases == []
    assert rows.items[0].version is None


def test_loads_aliases_and_version(tmp_path: Path):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text(
        "name,aliases,vendor,category,version,version_type,release_date,source_url\n"
        "Adobe Acrobat Reader,Acrobat Reader;Adobe Reader,Adobe,browser,2024.005.20320,software,2024-12-01,https://example.test/release\n",
        encoding="utf-8",
    )

    rows = CsvTargetLoader().load(csv_path)

    item = rows.items[0]
    assert item.target.aliases == ["Acrobat Reader", "Adobe Reader"]
    assert item.target.vendor == "Adobe"
    assert item.target.category == "browser"
    assert item.version is not None
    assert item.version.version == "2024.005.20320"
    assert item.version.version_type == "software"
    assert item.version.source_url == "https://example.test/release"


def test_preserves_only_non_empty_unknown_columns_as_raw_metadata(tmp_path: Path):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text(
        "name,notes,empty,spaces\nVMware Workstation,contest target,,   \n",
        encoding="utf-8",
    )

    rows = CsvTargetLoader().load(csv_path)

    assert rows.items[0].target.raw_metadata == {"notes": "contest target"}


def test_ignores_extra_unkeyed_fields_in_malformed_rows(tmp_path: Path):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text("name,notes\nTarget,ok,extra\n", encoding="utf-8")

    rows = CsvTargetLoader().load(csv_path)

    assert rows.errors == []
    assert rows.items[0].target.name == "Target"
    assert rows.items[0].target.raw_metadata == {"notes": "ok"}


def test_skips_missing_name_rows(tmp_path: Path):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text("name,aliases\n,Alias Only\nValid Target,Alias\n", encoding="utf-8")

    rows = CsvTargetLoader().load(csv_path)

    assert [item.target.name for item in rows.items] == ["Valid Target"]
    assert rows.errors == ["row 2: missing required name"]


def test_loads_vendor_alias_as_known_target_field(tmp_path: Path):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text(
        "name,vendor,vendor_alias,notes\n"
        "Canon MF654Cdw,Canon,mf654cdw,contest target\n",
        encoding="utf-8",
    )

    rows = CsvTargetLoader().load(csv_path)

    assert rows.errors == []
    assert rows.items[0].target.vendor_alias == "mf654cdw"
    assert rows.items[0].target.raw_metadata == {"notes": "contest target"}


def test_loads_search_names_semicolon_list(tmp_path: Path):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text(
        "name,aliases,search_names\nChroma,,ChromaDB\n",
        encoding="utf-8",
    )
    rows = CsvTargetLoader().load(csv_path)
    assert rows.items[0].target.search_names == ["ChromaDB"]
