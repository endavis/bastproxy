"""Tests for bound parameters and checked identifiers in Sqldb (#596)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from bastproxy.plugins.core.sqldb.libs._sqlite import Sqldb

SQL = """CREATE TABLE things(
    thing_id INTEGER NOT NULL PRIMARY KEY autoincrement,
    name TEXT NOT NULL,
    note TEXT
);"""
NOKEY_SQL = "CREATE TABLE loose(name TEXT);"


def _db(tmp_path: Path) -> Sqldb:
    db = Sqldb("tests.sqlparams", dbname="sqlparams", dbdir=tmp_path)
    db.addtable("things", SQL, keyfield="thing_id")
    db.addtable("loose", NOKEY_SQL)
    db.open()
    db.checktable("things")
    db.checktable("loose")
    return db


def _fake_api(args: dict[str, Any]) -> Callable[[str], Callable[..., Any]]:
    def api(name: str) -> Callable[..., Any]:
        if name.endswith("command.current.args.get"):
            return lambda: args
        if name.endswith("line.length.get"):
            return lambda: 80
        raise AssertionError(name)

    return api


def _col(rows: Any, key: str) -> list[Any]:
    return [r[key] for r in rows]


def _fill(db: Sqldb) -> None:
    db.modify("INSERT INTO things(name, note) VALUES (?, ?)", ("O'Brien", "a"))
    db.modify("INSERT INTO things(name, note) VALUES (?, ?)", ("b", None))
    db.modify("INSERT INTO things(name, note) VALUES (?, ?)", ("c", "a"))


def test_getrow_binds_value(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _fill(db)
    assert db.getrow(1, "things") == [{"thing_id": 1, "name": "O'Brien", "note": "a"}]
    assert db.getrow("1 OR 1=1", "things") == []  # type: ignore[arg-type]


def test_getlast_mapping(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _fill(db)
    rows = db.getlast("things", 5, {"note": "a"})
    assert _col(rows, "name") == ["c", "O'Brien"]
    rows = db.getlast("things", 5, {"name": "O'Brien"})
    assert _col(rows, "thing_id") == [1]
    rows = db.getlast("things", 5, {"note": None})
    assert _col(rows, "name") == ["b"]
    assert len(db.getlast("things", 2)) == 2


def test_getlast_unknown_column_raises(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with pytest.raises(ValueError, match="not a column"):
        db.getlast("things", 1, {"name = 1 OR note": "x"})


def test_getlast_string_where_warns(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _fill(db)
    with pytest.warns(DeprecationWarning):
        rows = db.getlast("things", 5, "note = 'a'")
    assert len(rows) == 2


def test_getlast_without_where_does_not_warn(tmp_path: Path) -> None:
    import warnings

    db = _db(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        db.getlast("things", 1)
        db.getlast("things", 1, {})


def test_no_keyfield_returns_empty(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert db.getrow(1, "loose") == {}
    assert db.getlast("loose", 1) == {}


def test_checktableexists(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert db.checktableexists("things")
    assert not db.checktableexists("nope")
    assert not db.checktableexists('x" OR "1"="1')


def test_setversion(tmp_path: Path) -> None:
    db = _db(tmp_path)
    db.setversion(3)
    assert db.getversion() == 3
    with pytest.raises(ValueError, match="invalid literal"):
        db.setversion("3; DROP TABLE things")  # type: ignore[arg-type]
    assert db.checktableexists("things")


def test_select_params_and_fixsql(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _fill(db)
    assert len(db.select("SELECT * FROM things WHERE name = ?", ("O'Brien",))) == 1
    assert len(db.select("SELECT * FROM things WHERE name = :n", {"n": "b"})) == 1
    with pytest.warns(DeprecationWarning):
        quoted = db.fixsql("O'Brien")
    assert quoted == "'O''Brien'"
    assert len(db.select(f"SELECT * FROM things WHERE name = {quoted}")) == 1


@pytest.mark.parametrize("name", ["../evil", "a/b", "a\\b", "", "..", "."])
def test_backupdb_refuses_unsafe_names(tmp_path: Path, name: str) -> None:
    db = _db(tmp_path)
    assert db.backupdb(name) is False
    assert not (tmp_path / "archive").exists()
    assert db.db_connection is not None


def test_backupdb_accepts_plain_name(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert db.backupdb("plain") is True
    assert (tmp_path / "archive" / "sqlparams_plain.sqlite.zip").exists()


@pytest.mark.parametrize("name", ["../evil", "a/b", "a\\b"])
def test_command_dbbackup_refuses(tmp_path: Path, name: str) -> None:
    db = _db(tmp_path)
    db.api = _fake_api({"name": name})  # type: ignore[assignment]
    result = db._command_dbbackup()
    assert "not a plain backup name" in result.message[0]
    assert not (tmp_path / "archive").exists()


def test_command_dbbackup_accepts_plain(tmp_path: Path) -> None:
    db = _db(tmp_path)
    db.api = _fake_api({"name": "plain"})  # type: ignore[assignment]
    result = db._command_dbbackup()
    assert result.message[0].startswith("backed up")


def test_command_dbtables(tmp_path: Path) -> None:
    db = _db(tmp_path)
    db.api = _fake_api({"table": "things"})  # type: ignore[assignment]
    result = db._command_dbtables()
    assert any(line.startswith("name") for line in result.message)
    db.api = _fake_api({"table": "nope"})  # type: ignore[assignment]
    assert "does not exist" in db._command_dbtables().message[0]
