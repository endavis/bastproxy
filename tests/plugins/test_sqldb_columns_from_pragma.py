"""Tests that Sqldb derives columns and defaults from sqlite itself (#594)."""

from pathlib import Path

import pytest

from bastproxy.plugins.core.sqldb.libs._sqlite import Sqldb


def _db(tmp_path: Path, sql: str, keyfield: str | None = None) -> Sqldb:
    db = Sqldb("tests.sqlcols", dbname="sqlcols", dbdir=tmp_path)
    db.addtable("t", sql, keyfield=keyfield)
    return db


def test_issue_reproduction(tmp_path: Path) -> None:
    db = _db(
        tmp_path,
        """CREATE TABLE t(
  t_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT DEFAULT "a" NOT NULL,
  score REAL DEFAULT (0),
  level INT)""",
        keyfield="t_id",
    )
    table = db.tables["t"]
    assert table.columns == ["t_id", "name", "score", "level"]
    assert table.default_column_values == {
        "t_id": None,
        "name": '"a"',
        "score": "0",
        "level": None,
    }
    assert db.converttoinsert("t") == "INSERT INTO t VALUES (:t_id, :name, :score, :level)"


def test_final_column_on_closing_paren_line(tmp_path: Path) -> None:
    db = _db(tmp_path, "CREATE TABLE t(a INT,\n b INT)")
    assert db.tables["t"].columns == ["a", "b"]


def test_type_size(tmp_path: Path) -> None:
    db = _db(tmp_path, "CREATE TABLE t(\n name VARCHAR(20),\n b INT\n)")
    assert db.tables["t"].columns == ["name", "b"]


def test_parenthesised_default(tmp_path: Path) -> None:
    db = _db(tmp_path, "CREATE TABLE t(\n score REAL DEFAULT (0),\n b INT\n)")
    assert db.tables["t"].columns == ["score", "b"]
    assert db.tables["t"].default_column_values["score"] == "0"


def test_uppercase_default(tmp_path: Path) -> None:
    db = _db(tmp_path, "CREATE TABLE t(\n level INT DEFAULT 5,\n b INT\n)")
    assert db.tables["t"].default_column_values["level"] == "5"


def test_default_then_not_null(tmp_path: Path) -> None:
    db = _db(tmp_path, "CREATE TABLE t(\n level INT DEFAULT 5 NOT NULL,\n b INT\n)")
    assert db.tables["t"].default_column_values["level"] == "5"


def test_several_columns_on_one_line(tmp_path: Path) -> None:
    db = _db(tmp_path, "CREATE TABLE t(a INT, b TEXT DEFAULT 'x', c INT)")
    assert db.tables["t"].columns == ["a", "b", "c"]
    assert db.tables["t"].default_column_values["b"] == "'x'"


def test_convert_include_every_column(tmp_path: Path) -> None:
    db = _db(tmp_path, "CREATE TABLE t(a INTEGER PRIMARY KEY, b INT, c INT)", keyfield="a")
    assert db.converttoinsert("t") == "INSERT INTO t VALUES (:a, :b, :c)"
    assert db.converttoupdate("t", wherekey="a") == "UPDATE t SET b = :b,c = :c WHERE a = :a;"
    assert db.checkdictforcolumns("t", {"b": 1}) == {"a": None, "b": 1, "c": None}
    assert db.checkcolumnexists("t", "c")


def test_old_names_still_work(tmp_path: Path) -> None:
    db = _db(tmp_path, "CREATE TABLE t(a INT, b INT)")
    assert db.checkcolumnumnexists("t", "b")
    assert db.checkdictforcolumnumns("t", {})["a"] is None
    assert db.getcolumnumnsfromsql("t")[0] == ["a", "b"]


def test_invalid_sql_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="could not read the columns"):
        _db(tmp_path, "CREATE TABLE t(")
