"""Tests for the SQLTable record held in Sqldb.tables (#419)."""

from pathlib import Path
from typing import Any

import pytest

from bastproxy.plugins.core.sqldb.libs._sqlite import Sqldb, SQLTable

SQL = """CREATE TABLE things(
    thing_id INTEGER NOT NULL PRIMARY KEY autoincrement,
    name TEXT NOT NULL,
    level INT default 1,
    note TEXT
);"""


def _db(tmp_path: Path) -> Sqldb:
    return Sqldb("tests.sqltables", dbname="sqltables", dbdir=tmp_path)


def test_defaults() -> None:
    table = SQLTable(name="t", createsql="x")
    assert table.keyfield is None
    assert table.precreate is None
    assert table.postcreate is None
    assert table.columns == []
    assert table.columns_by_keys == {}
    assert table.default_column_values == {}
    assert table.extra == {}


def test_addtable_builds_columns(tmp_path: Path) -> None:
    db = _db(tmp_path)
    db.addtable("things", SQL, keyfield="thing_id", custom=1)
    table = db.tables["things"]
    assert isinstance(table, SQLTable)
    assert table.keyfield == "thing_id"
    assert table.columns == ["thing_id", "name", "level", "note"]
    assert table.columns_by_keys == dict.fromkeys(table.columns, True)
    assert table.default_column_values["level"] == "1"
    assert table.default_column_values["name"] is None
    assert table.extra == {"custom": 1}
    assert db.checkcolumnumnexists("things", "level")
    assert not db.checkcolumnumnexists("things", "nope")
    assert db.checkdictforcolumnumns("things", {"name": "a"})["level"] == "1"
    assert db.converttoinsert("things", keynull=True) == (
        "INSERT INTO things VALUES (NULL, :name, :level, :note)"
    )
    assert "level = :level" in db.converttoupdate("things", wherekey="thing_id")


def test_missing_table_raises_keyerror(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with pytest.raises(KeyError):
        db.converttoinsert("missing")


def test_checktable_calls_hooks(tmp_path: Path) -> None:
    db = _db(tmp_path)
    calls: list[str] = []
    db.addtable(
        "things",
        SQL,
        keyfield="thing_id",
        precreate=lambda: calls.append("pre"),
        postcreate=lambda: calls.append("post"),
    )
    db.postinit()
    assert calls == ["pre", "post"]
    assert db.checktableexists("things")
    db.checktable("things")
    assert calls == ["pre", "post"]


def test_keyfield_readers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db(tmp_path)
    db.addtable("things", SQL, keyfield="thing_id")
    seen: list[str] = []

    def record(sql: str) -> list[Any]:
        seen.append(sql)
        return []

    def fake_api(name: str) -> Any:
        return record

    monkeypatch.setattr(db, "api", fake_api)
    db.getlast("things", 3)
    db.getrow(5, "things")
    db.getlastrowid("things")
    assert seen == [
        "SELECT * FROM things ORDER by thing_id desc limit 3",
        "SELECT * FROM things WHERE thing_id = 5",
        "SELECT MAX(thing_id) AS MAX FROM things",
    ]
    assert db.remove("nope", 2)[0] is False
