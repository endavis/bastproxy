"""Tests for the Sqldb lifecycle: lazy connection, errors, migrations, unload (#595)."""

import functools
import logging
import sqlite3
import types
import zipfile
from pathlib import Path
from typing import Any, ClassVar

import pytest

from bastproxy.plugins.core.sqldb.libs import _sqlite
from bastproxy.plugins.core.sqldb.libs._sqlite import (
    Sqldb,
    _split_script,
    _sql_default_to_value,
)
from bastproxy.plugins.core.sqldb.plugin._sqldb import SQLDBPlugin
from tests.plugins.test_sqldb_helpers import SQL, _db
from tests.plugins.test_sqldb_remove import _FakeApi

SQLITE_SOURCE = Path(_sqlite.__file__).read_text(encoding="utf-8")


def _plain(tmp_path: Path, plugin_id: str = "tests.lifecycle", name: str = "lifecycle") -> Sqldb:
    return Sqldb(plugin_id, dbname=name, dbdir=tmp_path)


def _tables(db: Sqldb) -> set[str]:
    rows = db.select("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row["name"] for row in rows}


def test_removed_machinery() -> None:
    assert "__getattribute__" not in Sqldb.__dict__
    assert not hasattr(Sqldb, "turnonpragmas")
    for banned in ("inspect.stack", "import inspect", "shutil", "turnonpragmas", ".connections"):
        assert banned not in SQLITE_SOURCE


def test_lazy_open_close_reopen(tmp_path: Path) -> None:
    db = _plain(tmp_path)
    assert db.db_connection is None
    db.select("SELECT 1 AS one")
    first = db.db_connection
    assert first is not None
    db.open()
    assert db.db_connection is first
    db.close()
    assert db.db_connection is None
    assert db.select("SELECT 1 AS one") == [{"one": 1}]
    assert db.db_connection is not None


def test_select_failure_raises_logs_and_recovers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db = _db(tmp_path)
    with caplog.at_level(logging.ERROR), pytest.raises(sqlite3.Error):
        db.select("SELECT * FROM nope")
    assert db._conn().in_transaction is False
    assert db.select("SELECT * FROM things") == []


def test_selectbykeyword_failure_raises(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with pytest.raises(sqlite3.Error):
        db.selectbykeyword("SELECT * FROM nope", "name")
    assert db._conn().in_transaction is False
    db.modify("INSERT INTO things(name) VALUES ('a')")
    assert db.selectbykeyword("SELECT * FROM things", "name")["a"]["name"] == "a"


def test_modify_failure_rolls_back(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert db.modify("INSERT INTO things(name) VALUES ('a')")[1] is None
    with pytest.raises(sqlite3.Error):
        db.modify("INSERT INTO things(name) VALUES (NULL)")
    assert db._conn().in_transaction is False
    assert len(db.select("SELECT * FROM things")) == 1


def test_modify_returns_rowid(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert db.modify("INSERT INTO things(name) VALUES ('a')") == (1, None)
    assert db.modify("INSERT INTO things(name) VALUES (:n)", {"n": "b"}) == (2, None)


def test_modifymany_is_all_or_none(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert db.modifymany("INSERT INTO things(name) VALUES (?)", []) == (-1, [])
    with pytest.raises(sqlite3.Error):
        db.modifymany("INSERT INTO things(name) VALUES (?)", [("a",), (None,)])
    assert db._conn().in_transaction is False
    assert db.select("SELECT * FROM things") == []
    db.modifymany("INSERT INTO things(name) VALUES (?)", [("a",), ("b",)])
    assert len(db.select("SELECT * FROM things")) == 2


def test_modifyscript_is_all_or_none(tmp_path: Path) -> None:
    db = _db(tmp_path)
    script = (
        "CREATE TABLE extra(x INTEGER); INSERT INTO extra VALUES (1); INSERT INTO nope VALUES (1);"
    )
    with pytest.raises(sqlite3.Error):
        db.modifyscript(script)
    assert db._conn().in_transaction is False
    assert "extra" not in _tables(db)
    db.modifyscript("CREATE TABLE extra(x INTEGER); INSERT INTO extra VALUES (1);")
    assert db.select("SELECT * FROM extra") == [{"x": 1}]


def test_each_failure_is_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    db = _db(tmp_path)
    with caplog.at_level(logging.ERROR):
        for call in (
            lambda: db.select("SELECT * FROM nope"),
            lambda: db.modify("INSERT INTO nope VALUES (1)"),
        ):
            before = len(caplog.records)
            with pytest.raises(sqlite3.Error):
                call()
            assert len(caplog.records) > before


def test_split_script_keeps_triggers_and_quoted_semicolons() -> None:
    script = (
        "CREATE TABLE t(a TEXT DEFAULT ';', b INTEGER);\n"
        "CREATE TRIGGER trg AFTER INSERT ON t BEGIN UPDATE t SET b = 1; "
        "DELETE FROM t WHERE b = 2; END;\n"
    )
    statements = _split_script(script)
    assert len(statements) == 2
    assert statements[1].lstrip().startswith("CREATE TRIGGER")


def test_modifyscript_runs_trigger_and_semicolon_default(tmp_path: Path) -> None:
    db = _plain(tmp_path)
    db.modifyscript(
        "CREATE TABLE t(a TEXT DEFAULT ';', b INTEGER);"
        "CREATE TRIGGER trg AFTER INSERT ON t BEGIN UPDATE t SET b = 7; END;"
    )
    db.modify("INSERT INTO t(b) VALUES (1)")
    assert db.select("SELECT a, b FROM t") == [{"a": ";", "b": 7}]


def _versioned(tmp_path: Path, steps: dict[int, Any], version: int) -> Sqldb:
    _db(tmp_path).close()
    db = _plain(tmp_path, "tests.sqlhelpers", "sqlhelpers")
    db.version = version
    db.version_functions.update(steps)
    db.addtable("things", SQL, keyfield="thing_id")
    return db


def test_failed_step_keeps_earlier_steps(tmp_path: Path) -> None:
    holder: list[Sqldb] = []

    def step3() -> None:
        holder[0].modifyscript("CREATE TABLE three(x INTEGER)")
        raise RuntimeError("boom")

    db = _versioned(
        tmp_path,
        {2: lambda: holder[0].modifyscript("CREATE TABLE two(x INTEGER)"), 3: step3},
        3,
    )
    holder.append(db)
    with pytest.raises(RuntimeError):
        db.postinit()
    assert db.getversion() == 2
    tables = _tables(db)
    assert "two" in tables
    assert "three" not in tables


def test_missing_step_raises_before_any_change(tmp_path: Path) -> None:
    ran: list[int] = []
    db = _versioned(tmp_path, {3: lambda: ran.append(3)}, 3)
    with pytest.raises(ValueError, match=r"\[2\]"):
        db.postinit()
    assert db.getversion() == 1
    assert ran == []
    assert not (tmp_path / "archive").exists() or not list((tmp_path / "archive").iterdir())


def test_step_using_modify_nests_and_rolls_back(tmp_path: Path) -> None:
    holder: list[Sqldb] = []

    def step2() -> None:
        holder[0].modify("INSERT INTO things(name) VALUES ('x')")
        raise RuntimeError("boom")

    db = _versioned(tmp_path, {2: step2}, 2)
    holder.append(db)
    with pytest.raises(RuntimeError):
        db.postinit()
    assert db.select("SELECT * FROM things") == []
    assert db.getversion() == 1


def test_backup_keeps_connection_and_zip_is_readable(tmp_path: Path) -> None:
    db = _db(tmp_path)
    db.modify("INSERT INTO things(name) VALUES ('a')")
    connection = db.db_connection
    assert db.backupdb("v1") is True
    assert db.db_connection is connection
    archive = tmp_path / "archive" / "sqlhelpers_v1.sqlite.zip"
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(tmp_path / "unzipped")
    restored = sqlite3.connect(tmp_path / "unzipped" / "sqlhelpers_v1.sqlite")
    try:
        assert restored.execute("SELECT name FROM things").fetchall() == [("a",)]
    finally:
        restored.close()


def _command_db(tmp_path: Path, args: dict[str, Any]) -> Sqldb:
    db = _plain(tmp_path)
    db.api = _FakeApi(db, args)  # type: ignore[assignment]
    return db


def test_dbselect_and_dbmodify_report_errors(tmp_path: Path) -> None:
    db = _plain(tmp_path)

    def route(args: dict[str, Any]) -> Any:
        def api(name: str) -> Any:
            if name.endswith(":command.current.args.get"):
                return lambda: args
            return db.select if name.endswith(".select") else db.modify

        return api

    db.api = route({"stmt": "SELECT * FROM nope"})
    result = db._command_dbselect()
    assert result.success is True
    assert "no such table" in result.message[0]
    db.api = route({"stmt": "INSERT INTO nope VALUES (1)"})
    assert "no such table" in db._command_dbmodify().message[0]


def test_other_commands_report_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise sqlite3.OperationalError("kaboom")

    db = _command_db(tmp_path, {"table": "", "name": "n", "rownumber": 1})
    db.addtable("things", SQL, keyfield="thing_id")
    monkeypatch.setattr(db, "_conn", boom)
    assert "kaboom" in db._command_dbvac().message[0]
    assert "kaboom" in db._command_dbtables().message[0]
    assert "kaboom" in db._command_dbbackup().message[0]
    monkeypatch.undo()
    monkeypatch.setattr(db, "modify", boom)
    db.api = _FakeApi(db, {"table": "things", "rownumber": 1})  # type: ignore[assignment]
    assert "kaboom" in db._command_dbremove().message[0]


class _FakeRegisterApi:
    """An API stand-in that reports and records sqldb registration."""

    registered: ClassVar[list[Sqldb]] = []
    BASEPATH = Path()

    def __init__(self, owner_id: str = "") -> None:
        self.owner_id = owner_id

    def __call__(self, name: str) -> Any:
        if name == "libs.api:api.exists":
            return lambda api: True
        assert name == "plugins.core.sqldb:database.register"
        return self.registered.append


def test_construction_registers_when_api_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _FakeRegisterApi.registered = []
    monkeypatch.setattr(_sqlite, "API", _FakeRegisterApi)
    db = _plain(tmp_path)
    assert _FakeRegisterApi.registered == [db]


def test_construction_without_register_api_works(tmp_path: Path) -> None:
    assert _plain(tmp_path).select("SELECT 1 AS one") == [{"one": 1}]


def _plugin_namespace() -> Any:
    ns = types.SimpleNamespace(plugin_id="plugins.core.sqldb", databases={})
    ns._close_databases_for = functools.partial(SQLDBPlugin._close_databases_for, ns)  # type: ignore[arg-type]
    ns.register = functools.partial(SQLDBPlugin._api_database_register, ns)
    return ns


def test_unload_closes_only_that_plugins_databases(tmp_path: Path) -> None:
    ns = _plugin_namespace()
    a1 = _plain(tmp_path, "plugins.a", "a1")
    a2 = _plain(tmp_path, "plugins.a", "a2")
    b1 = _plain(tmp_path, "plugins.b", "b1")
    for db in (a1, a2, b1):
        db.open()
        ns.register(db)
    ns.api = lambda name: lambda: {"plugin_id": "plugins.a"}
    SQLDBPlugin._eventcb_plugin_unloaded(ns)
    assert a1.db_connection is None
    assert a2.db_connection is None
    assert b1.db_connection is not None
    assert list(ns.databases) == ["plugins.b"]


def test_unload_handler_is_registered_to_the_event() -> None:
    registrations = SQLDBPlugin._eventcb_plugin_unloaded.event_registration
    assert registrations[0]["event_name"] == "ev_plugin_unloaded"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, None),
        ("NULL", None),
        ('"a"', "a"),
        ("'x'", "x"),
        ("'it''s'", "it's"),
        ("1", "1"),
    ],
)
def test_sql_default_to_value(text: str | None, expected: str | None) -> None:
    assert _sql_default_to_value(text) == expected


def test_string_default_inserted_without_quotes(tmp_path: Path) -> None:
    db = _plain(tmp_path)
    db.addtable(
        "t",
        'CREATE TABLE t(t_id INTEGER PRIMARY KEY, label TEXT DEFAULT "a", n INTEGER DEFAULT 1);',
        keyfield="t_id",
    )
    db.postinit()
    row = db.checkdictforcolumns("t", {"t_id": 1})
    assert row == {"t_id": 1, "label": "a", "n": "1"}
    db.modify(db.converttoinsert("t"), row)
    assert db.select("SELECT label FROM t") == [{"label": "a"}]
