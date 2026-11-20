"""Tests for the sqldb ``db*`` commands with more than one database (#603)."""

import argparse
import sqlite3
import types
import zipfile
from pathlib import Path
from typing import Any

import pytest

from bastproxy.libs.api import API
from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.sqldb.libs._sqlite import Sqldb, create_database
from bastproxy.plugins.core.sqldb.plugin._sqldb import SQLDBPlugin

OWNER = "plugins.test.multi603"
SQL = (
    "CREATE TABLE things(thing_id INTEGER NOT NULL PRIMARY KEY autoincrement, name TEXT NOT NULL);"
)
TABLE: dict[str, Any] = {"name": "things", "sql": SQL, "keyfield": "thing_id"}
ALL_COMMANDS = [
    "_command_dbselect",
    "_command_dbtables",
    "_command_dbmodify",
    "_command_dbvac",
    "_command_dbclose",
    "_command_dbremove",
    "_command_dbbackup",
]


class _Args:
    """A command API stand-in: current args plus the per-database select/modify."""

    def __init__(self, args: dict[str, Any], dbs: list[Sqldb]) -> None:
        self.args = args
        self.dbs = dbs

    def __call__(self, name: str) -> Any:
        if name.endswith(":command.current.args.get"):
            return lambda: self.args
        if name.endswith(":line.length.get"):
            return lambda: 80
        if name.endswith((".select", ".modify")):
            database = next(
                d for d in self.dbs if name.startswith(f"{d.plugin_id}:{d.database_name}.")
            )
            return database.select if name.endswith(".select") else database.modify
        raise AssertionError(name)


def _plugin(tmp_path: Path) -> Any:
    api = API(owner_id="plugins.core.sqldb")
    api.BASEDATAPLUGINPATH = tmp_path
    plugin = types.SimpleNamespace(databases={}, api=api, plugin_id="plugins.core.sqldb")
    for name in ("_api_database_register", "_api_database_add", "_close_databases_for"):
        setattr(plugin, name, types.MethodType(getattr(SQLDBPlugin, name), plugin))
    api.add("libs.plugins.loader", "plugin.id.is.valid", lambda pid: pid == OWNER, instance=True)
    api.add("libs.plugins.loader", "plugin.is.instantiated", lambda pid: True, instance=True)
    api.add("plugins.core.commands", "command.add.by.func", lambda func: None, instance=True)
    return plugin


def _two(tmp_path: Path) -> tuple[Sqldb, Sqldb]:
    plugin = _plugin(tmp_path)
    alpha = plugin._api_database_add(OWNER, "alpha", [TABLE])
    beta = plugin._api_database_add(OWNER, "beta", [TABLE])
    alpha.modify("INSERT INTO things(name) VALUES ('a1')")
    beta.modify("INSERT INTO things(name) VALUES ('b1')")
    beta.modify("INSERT INTO things(name) VALUES ('b2')")
    return alpha, beta


def _run(source: Sqldb, command: str, **args: Any) -> CommandResult:
    args.setdefault("db", "")
    dbs = source._command_candidates()
    for database in dbs:
        database.api = _Args(args, dbs)  # type: ignore[assignment]
    result: CommandResult = getattr(source, command)()
    return result


def _count(db: Sqldb) -> int:
    return int(db.select("SELECT COUNT(*) AS n FROM things")[0]["n"])


def _text(result: CommandResult) -> str:
    return "\n".join(result.message)


def test_single_database_acts_without_db(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path)
    db = plugin._api_database_add(OWNER, "solo", [TABLE])
    db.modify("INSERT INTO things(name) VALUES ('x')")
    assert "'x'" in _text(_run(db, "_command_dbselect", stmt="SELECT name FROM things"))
    assert _text(_run(db, "_command_dbtables", table="")).startswith("Tables in database solo:")
    assert "Fields in table things:" in _text(_run(db, "_command_dbtables", table="things"))
    assert _run(db, "_command_dbvac").message == ["Database Vacuumed"]
    assert _run(db, "_command_dbbackup", name="n1").message[0].startswith("backed up solo")


def test_single_database_accepts_its_name_and_rejects_wrong(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path)
    db = plugin._api_database_add(OWNER, "solo", [TABLE])
    assert _run(db, "_command_dbvac", db="solo").message == ["Database Vacuumed"]
    result = _run(db, "_command_dbvac", db="wrong")
    assert "Unknown database wrong" in _text(result)
    assert "solo" in _text(result)


def test_db_selects_each_database_from_either_bound_command(tmp_path: Path) -> None:
    alpha, beta = _two(tmp_path)
    stmt = "SELECT name FROM things"
    assert "a1" in _text(_run(beta, "_command_dbselect", db="alpha", stmt=stmt))
    assert "b1" in _text(_run(beta, "_command_dbselect", db="beta", stmt=stmt))
    assert "b1" not in _text(_run(alpha, "_command_dbselect", db="alpha", stmt=stmt))


@pytest.mark.parametrize("command", [c for c in ALL_COMMANDS if c != "_command_dbtables"])
def test_several_databases_without_db_errors_and_changes_nothing(
    tmp_path: Path, command: str
) -> None:
    alpha, beta = _two(tmp_path)
    result = _run(
        alpha, command, stmt="DELETE FROM things", table="things", rownumber=1, name="nope"
    )
    assert "alpha, beta" in _text(result)
    assert "--db" in _text(result)
    assert (_count(alpha), _count(beta)) == (1, 2)
    assert alpha.db_connection is not None
    assert not list(tmp_path.rglob("*nope*"))


def test_dbtables_lists_all_and_table_needs_db(tmp_path: Path) -> None:
    alpha, _ = _two(tmp_path)
    text = _text(_run(alpha, "_command_dbtables", table=""))
    assert text.index("Tables in database alpha:") < text.index("Tables in database beta:")
    assert "Fields in table" in _text(_run(alpha, "_command_dbtables", db="beta", table="things"))
    assert "--db" in _text(_run(alpha, "_command_dbtables", table="things"))
    only_beta = _text(_run(alpha, "_command_dbtables", db="beta", table=""))
    assert "alpha" not in only_beta


def test_dbclose_closes_only_the_target(tmp_path: Path) -> None:
    alpha, beta = _two(tmp_path)
    assert "alpha was closed" in _text(_run(beta, "_command_dbclose", db="alpha"))
    assert alpha.db_connection is None
    assert beta.db_connection is not None


def test_dbbackup_writes_only_the_target(tmp_path: Path) -> None:
    alpha, _ = _two(tmp_path)
    _run(alpha, "_command_dbbackup", db="beta", name="n1")
    files = list(tmp_path.rglob("*.zip"))
    assert [p.name for p in files] == ["beta_n1.sqlite.zip"]
    assert zipfile.is_zipfile(files[0])


def test_dbremove_and_dbmodify_target_one_database(tmp_path: Path) -> None:
    alpha, beta = _two(tmp_path)
    _run(alpha, "_command_dbremove", db="beta", table="things", rownumber=1)
    assert (_count(alpha), _count(beta)) == (1, 1)
    _run(beta, "_command_dbmodify", db="alpha", stmt="DELETE FROM things")
    assert (_count(alpha), _count(beta)) == (0, 1)


@pytest.mark.parametrize("command", ALL_COMMANDS)
def test_every_command_declares_db_option(command: str) -> None:
    arguments = getattr(Sqldb, command).command_data.arguments
    db_args = [a for a in arguments if a["args"] == ("--db",)]
    assert len(db_args) == 1
    assert db_args[0]["kwargs"]["default"] == ""
    for arg in arguments:
        assert "{" not in str(arg["kwargs"].get("help", ""))


def test_positional_parse_is_compatible() -> None:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    for arg in Sqldb._command_dbremove.command_data.arguments:
        parser.add_argument(*arg["args"], **arg["kwargs"])
    first = parser.parse_args(["things", "3"])
    assert (first.db, first.table, first.rownumber) == ("", "things", 3)
    second = parser.parse_args(["--db", "x", "things", "3"])
    assert (second.db, second.table, second.rownumber) == ("x", "things", 3)


def test_owner_databases_is_tracked_set_and_plain_db_targets_itself(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path)
    db = plugin._api_database_add(OWNER, "alpha", [TABLE])
    assert db.owner_databases is plugin.databases[OWNER]
    plain = Sqldb("tests.plain603", dbname="plain", dbdir=tmp_path / "plain")
    assert plain.owner_databases is None
    assert plain._command_target({"db": ""}) is plain


def test_failed_add_is_not_a_sibling_candidate(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path)
    alpha = plugin._api_database_add(OWNER, "alpha", [TABLE])
    bad = {"name": "bad", "sql": "CREATE TABLE bad(x INTEGER); INSERT INTO missing VALUES (1);"}
    with pytest.raises((ValueError, sqlite3.Error)):
        plugin._api_database_add(OWNER, "beta", [bad])
    assert [db.database_name for db in alpha._command_candidates()] == ["alpha"]


def test_create_database_directly_still_works(tmp_path: Path) -> None:
    db = create_database(OWNER, "direct", [TABLE], directory=tmp_path)
    assert db._command_candidates() == [db]
