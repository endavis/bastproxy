"""Tests for the sqldb remove command and Sqldb.remove (#441)."""

import argparse
from pathlib import Path
from typing import Any

from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.sqldb.libs._sqlite import Sqldb

SQL = """CREATE TABLE things(
    thing_id INTEGER NOT NULL PRIMARY KEY autoincrement,
    name TEXT NOT NULL
);"""


class _FakeApi:
    """Routes the api calls remove and the command make."""

    def __init__(self, db: Sqldb, args: dict[str, Any]) -> None:
        self.db = db
        self.args = args

    def __call__(self, name: str) -> Any:
        if name.endswith(":command.current.args.get"):
            return lambda: self.args
        assert name.endswith(".modify")
        return self.db.modify


def _db(tmp_path: Path, args: dict[str, Any] | None = None) -> Sqldb:
    db = Sqldb("tests.sqlremove", dbname="sqlremove", dbdir=tmp_path)
    db.api = _FakeApi(db, args or {})  # type: ignore[assignment]
    db.open()
    db.addtable("things", SQL, keyfield="thing_id")
    db.postinit()
    db.modify("INSERT INTO things(name) VALUES ('a')")
    db.modify("INSERT INTO things(name) VALUES ('b')")
    return db


def _ids(db: Sqldb) -> list[int]:
    return [row["thing_id"] for row in db.select("SELECT thing_id FROM things ORDER BY 1")]


def test_remove_deletes_row(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert db.remove("things", 1) == (True, "1 was removed from table things")
    assert _ids(db) == [2]


def test_remove_unknown_table(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert db.remove("nope", 1) == (False, "nope is not a table")
    assert _ids(db) == [1, 2]


def test_remove_table_without_keyfield(tmp_path: Path) -> None:
    db = _db(tmp_path)
    db.tables["things"].keyfield = None
    assert db.remove("things", 1) == (False, "things has no key field")
    assert _ids(db) == [1, 2]


def test_remove_row_number_is_bound(tmp_path: Path) -> None:
    db = _db(tmp_path)
    db.remove("things", "1 OR 1=1")
    assert _ids(db) == [1, 2]


def test_command_removes_row(tmp_path: Path) -> None:
    db = _db(tmp_path, {"table": "things", "rownumber": 2})
    assert db._command_dbremove() == CommandResult(True, ["2 was removed from table things"])
    assert _ids(db) == [1]


def test_command_rejects_bad_input(tmp_path: Path) -> None:
    for index, (args, text) in enumerate(
        [
            ({"table": "nope", "rownumber": 1}, "valid table"),
            ({"table": "", "rownumber": 1}, "valid table"),
            ({"table": "things", "rownumber": -1}, "valid row number"),
            ({"table": "things", "rownumber": 0}, "valid row number"),
        ]
    ):
        db = _db(tmp_path / str(index), args)
        result = db._command_dbremove()
        message = result.message
        assert text in message[0]
        assert _ids(db) == [1, 2]
        db.close()


def test_rownumber_argument_parses_as_int() -> None:
    parser = argparse.ArgumentParser()
    for arg in Sqldb._command_dbremove.command_data.arguments:
        parser.add_argument(*arg["args"], **arg["kwargs"])
    parsed = parser.parse_args(["things", "3"])
    assert parsed.rownumber == 3
    assert parser.parse_args([]).rownumber == -1
