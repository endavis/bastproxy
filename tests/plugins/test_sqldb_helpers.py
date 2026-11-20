"""Tests for Sqldb backup, checktable, fixsql and row helpers (#593)."""

import zipfile
from pathlib import Path

from bastproxy.plugins.core.sqldb.libs._sqlite import Sqldb

SQL = """CREATE TABLE things(
    thing_id INTEGER NOT NULL PRIMARY KEY autoincrement,
    name TEXT NOT NULL
);"""


def _db(tmp_path: Path) -> Sqldb:
    db = Sqldb("tests.sqlhelpers", dbname="sqlhelpers", dbdir=tmp_path)
    db.addtable("things", SQL, keyfield="thing_id")
    db.postinit()
    return db


def test_backup_template_formats(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert db.backup_template % "v1" == "sqlhelpers_v1.sqlite"


def test_backupdb_creates_zip(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert db.backupdb("v1") is True
    archive = tmp_path / "archive" / "sqlhelpers_v1.sqlite.zip"
    assert archive.exists()
    assert zipfile.ZipFile(archive).namelist() == ["sqlhelpers_v1.sqlite"]


def test_upgrade_runs_version_function(tmp_path: Path) -> None:
    db = _db(tmp_path)
    db.close()
    ran: list[int] = []
    db2 = Sqldb("tests.sqlhelpers", dbname="sqlhelpers", dbdir=tmp_path)
    db2.version = 2
    db2.version_functions[2] = lambda: ran.append(2)
    db2.addtable("things", SQL, keyfield="thing_id")
    db2.postinit()
    assert ran == [2]


def test_checktable_unknown_table_returns_false(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert db.checktable("nope") is False
    assert db.checktable("things") is True


def test_fixsql_none_is_null(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert db.fixsql(None) == "NULL"
    assert db.fixsql("a'b") == "'a''b'"
    assert db.fixsql(None, like=True) == "NULL"


def test_row_helpers_use_self_select(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert db.getlastrowid("things") == -1
    db.modify("INSERT INTO things(name) VALUES ('a')")
    db.modify("INSERT INTO things(name) VALUES ('b')")
    assert db.getlastrowid("things") == 2
    assert db.getrow(1, "things") == [{"thing_id": 1, "name": "a"}]
    last = db.getlast("things", 1)
    assert isinstance(last, list)
    assert [r["name"] for r in last] == ["b"]
