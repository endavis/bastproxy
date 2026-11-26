"""Tests for the ``database.add`` factory API (#597)."""

import contextlib
import sqlite3
import types
import warnings
import zipfile
from pathlib import Path
from typing import Any

import pytest

from bastproxy.libs.api import API
from bastproxy.plugins.core.sqldb.libs._sqlite import Sqldb, create_database
from bastproxy.plugins.core.sqldb.plugin._sqldb import SQLDBPlugin

OWNER = "plugins.test.create597"
OTHER = "plugins.test.other597"
SQL = (
    "CREATE TABLE things(thing_id INTEGER NOT NULL PRIMARY KEY autoincrement, name TEXT NOT NULL);"
)
TABLE: dict[str, Any] = {"name": "things", "sql": SQL, "keyfield": "thing_id"}
COMMANDS = {
    "_command_dbselect",
    "_command_dbtables",
    "_command_dbmodify",
    "_command_dbvac",
    "_command_dbclose",
    "_command_dbremove",
    "_command_dbbackup",
}


def _make(tmp_path: Path, **kwargs: Any) -> Sqldb:
    return create_database(OWNER, "things_db", [TABLE], directory=tmp_path, **kwargs)


def _plugin(tmp_path: Path, added: list[Any] | None = None, with_commands: bool = True) -> Any:
    """A stand-in sqldb plugin whose api is a real API plus a recording command API."""
    api = API(owner_id="plugins.core.sqldb")
    api.BASEDATAPLUGINPATH = tmp_path
    plugin = types.SimpleNamespace(databases={}, api=api, plugin_id="plugins.core.sqldb")
    for name in ("_api_database_register", "_api_database_add", "_close_databases_for"):
        setattr(plugin, name, types.MethodType(getattr(SQLDBPlugin, name), plugin))
    api.add(
        "libs.plugins.loader",
        "plugin.id.is.valid",
        lambda pid: pid in {OWNER, OTHER},
        instance=True,
    )
    api.add("libs.plugins.loader", "plugin.is.instantiated", lambda pid: True, instance=True)
    if with_commands:
        api.add(
            "plugins.core.commands",
            "command.add.by.func",
            (added if added is not None else []).append,
            instance=True,
        )
    return plugin


def _registered(api: API, name: str) -> bool:
    try:
        api.get(name)
    except (KeyError, AttributeError, ValueError):
        return False
    return True


def test_create_returns_ready_db(tmp_path: Path) -> None:
    db = _make(tmp_path)
    assert (tmp_path / "things_db.sqlite").exists()
    assert db.checktableexists("things")
    assert db.getversion() == 1


def test_hooks_run_once_on_fresh_database(tmp_path: Path) -> None:
    seen: list[tuple[str, Any]] = []
    table = {
        **TABLE,
        "precreate": lambda db: seen.append(("pre", db)),
        "postcreate": lambda db: seen.append(("post", db)),
    }
    db = create_database(OWNER, "hooks", [table], directory=tmp_path)
    assert seen == [("pre", db), ("post", db)]
    db.close()
    create_database(OWNER, "hooks", [table], directory=tmp_path)
    assert len(seen) == 2


def test_sql_migration_adds_column_and_backs_up(tmp_path: Path) -> None:
    _make(tmp_path).close()
    db = _make(
        tmp_path,
        version=2,
        migrations={2: "ALTER TABLE things ADD COLUMN extra TEXT;"},
    )
    assert db.getversion() == 2
    assert db.select("SELECT extra FROM things") == []
    backup = tmp_path / "archive" / "things_db_1.sqlite.zip"
    assert zipfile.ZipFile(backup).namelist() == ["things_db_1.sqlite"]


def test_callable_migration_receives_db(tmp_path: Path) -> None:
    _make(tmp_path).close()
    received: list[Sqldb] = []

    def step(db: Sqldb) -> None:
        received.append(db)
        db.modify("INSERT INTO things(name) VALUES ('kept')")

    db = _make(tmp_path, version=2, migrations={2: step})
    assert received == [db]
    assert db.select("SELECT name FROM things") == [{"name": "kept"}]


def test_fresh_database_at_higher_version_skips_steps(tmp_path: Path) -> None:
    ran: list[int] = []
    db = _make(
        tmp_path, version=3, migrations={2: lambda d: ran.append(2), 3: lambda d: ran.append(3)}
    )
    assert ran == []
    assert db.getversion() == 3


@pytest.mark.parametrize(
    ("tables", "name", "version", "migrations"),
    [
        ([{**TABLE, "bogus": 1}], "okname", 1, None),
        ([{"name": "things"}], "okname", 1, None),
        ([{**TABLE, "precreate": "nope"}], "okname", 1, None),
        ([TABLE, TABLE], "okname", 1, None),
        ([TABLE], "Bad", 1, None),
        ([TABLE], "1bad", 1, None),
        ([TABLE], "bad-name", 1, None),
        ([TABLE], "", 1, None),
        ([TABLE], "okname", 0, None),
        ([TABLE], "okname", 3, {2: "SELECT 1;"}),
        ([TABLE], "okname", 2, {2: "SELECT 1;", 3: "SELECT 1;"}),
        ([TABLE], "okname", 1, {2: "SELECT 1;"}),
        ([TABLE], "okname", 2, {2: 5}),
        ([TABLE], "okname", 2, {"2": "SELECT 1;"}),
        ("things", "okname", 1, None),
        ([{**TABLE, "name": "bad name"}], "okname", 1, None),
    ],
)
def test_invalid_definitions_raise_and_create_nothing(
    tmp_path: Path, tables: Any, name: str, version: int, migrations: Any
) -> None:
    with pytest.raises(ValueError):
        create_database(
            OWNER, name, tables, version=version, migrations=migrations, directory=tmp_path
        )
    assert list(tmp_path.iterdir()) == []


def test_failed_migration_reraises_and_closes(tmp_path: Path) -> None:
    _make(tmp_path).close()
    plugin = _plugin(tmp_path)
    with pytest.raises(sqlite3.Error):
        plugin._api_database_add(
            OWNER,
            "things_db",
            [TABLE],
            version=2,
            migrations={2: "ALTER TABLE nope ADD COLUMN x TEXT;"},
            directory=tmp_path,
        )
    assert plugin.databases.get(OWNER, set()) == set()


def test_duplicate_owner_and_name_refused_but_other_owner_works(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path)
    plugin._api_database_add(OWNER, "dup", [TABLE])
    with pytest.raises(ValueError, match="already has a database"):
        plugin._api_database_add(OWNER, "dup", [TABLE])
    other = plugin._api_database_add(OTHER, "dup", [TABLE])
    assert other.plugin_id == OTHER
    assert (tmp_path / OTHER / "dup.sqlite").exists()
    plugin.api("libs.api:api.toplevel.remove")(OWNER)
    plugin.api("libs.api:api.toplevel.remove")(OTHER)


def test_unknown_owner_refused(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path)
    with pytest.raises(ValueError, match="not a plugin id"):
        plugin._api_database_add("plugins.test.unknown597", "x", [TABLE])
    assert not (tmp_path / "plugins.test.unknown597").exists()


def test_apis_registered_under_owner(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path)
    db = plugin._api_database_add(OWNER, "apidb", [TABLE])
    api = plugin.api
    try:
        for suffix in ("select", "modify", "modify.many", "row.get"):
            assert _registered(api, f"{OWNER}:apidb.{suffix}")
        api(f"{OWNER}:apidb.modify")("INSERT INTO things(name) VALUES ('a')")
        assert api(f"{OWNER}:apidb.select")("SELECT name FROM things") == [{"name": "a"}]
        assert db.remove("things", 1)[0] is True
        assert api(f"{OWNER}:apidb.row.get")(1, "things") == []
    finally:
        api("libs.api:api.toplevel.remove")(OWNER)


def test_commands_registered_bound_to_db(tmp_path: Path) -> None:
    added: list[Any] = []
    plugin = _plugin(tmp_path, added)
    db = plugin._api_database_add(OWNER, "cmddb", [TABLE])
    try:
        assert {c.__name__ for c in added} == COMMANDS
        assert all(c.__self__ is db and c.__self__.plugin_id == OWNER for c in added)
    finally:
        plugin.api("libs.api:api.toplevel.remove")(OWNER)


def test_create_works_without_commands_api(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path, with_commands=False)
    db = plugin._api_database_add(OWNER, "nocmd", [TABLE])
    try:
        assert isinstance(db, Sqldb)
    finally:
        plugin.api("libs.api:api.toplevel.remove")(OWNER)


def test_unload_closes_and_untracks(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path)
    db = plugin._api_database_add(OWNER, "unl", [TABLE])
    db.select("SELECT 1")
    assert db.db_connection is not None
    plugin.api("libs.api:api.toplevel.remove")(OWNER)
    plugin._close_databases_for(OWNER)
    assert db.db_connection is None
    assert OWNER not in plugin.databases
    assert not _registered(plugin.api, f"{OWNER}:unl.select")


def test_default_directory_is_owner_data_dir(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path)
    db = plugin._api_database_add(OWNER, "defdir", [TABLE])
    try:
        assert db.db_file == tmp_path / OWNER / "defdir.sqlite"
    finally:
        plugin.api("libs.api:api.toplevel.remove")(OWNER)


def test_generated_api_names_pass_grammar(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path)
    plugin._api_database_add(OWNER, "gram", [TABLE])
    try:
        names = plugin.api("libs.api:api.list.in.toplevel")(OWNER)
        assert names
        assert all(n.startswith("gram.") for n in names)
    finally:
        plugin.api("libs.api:api.toplevel.remove")(OWNER)


def test_baseclass_get_warns() -> None:
    with pytest.warns(DeprecationWarning, match="database.add"):
        assert SQLDBPlugin._api_baseclass_get(None) is Sqldb


def test_create_does_not_import_other_plugins() -> None:
    source = (
        Path(__file__).parents[2] / "src/bastproxy/plugins/test/_sqldb/plugin/_sqldb.py"
    ).read_text(encoding="utf-8")
    assert "bastproxy.plugins.core" not in source
    warnings.simplefilter("default")


def _mode(db: Sqldb) -> str:
    return str(db.select("PRAGMA journal_mode")[0]["journal_mode"])


def test_journal_mode_wal_set_and_reapplied_after_reopen(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path)
    db = plugin._api_database_add(OWNER, "waldb", [TABLE], journal_mode="WAL")
    assert _mode(db) == "wal"
    # make the file leave wal behind our back, so only a re-applied pragma can restore it
    db.close()
    with contextlib.closing(sqlite3.connect(tmp_path / "waldb.sqlite")) as raw:
        raw.execute("PRAGMA journal_mode=delete")
    assert _mode(db) == "wal"


def test_journal_mode_default_is_delete(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path)
    db = plugin._api_database_add(OWNER, "plaindb", [TABLE])
    assert _mode(db) == "delete"


def test_unknown_journal_mode_raises_and_creates_nothing(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path)
    with pytest.raises(ValueError, match="journal mode"):
        plugin._api_database_add(OWNER, "baddb", [TABLE], journal_mode="bogus")
    assert list(tmp_path.iterdir()) == []


def test_journal_mode_mismatch_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db = _make(tmp_path)
    fake = types.SimpleNamespace(
        execute=lambda sql: types.SimpleNamespace(fetchone=lambda: {"journal_mode": "delete"})
    )
    with caplog.at_level("WARNING"):
        db._apply_journal_mode(fake, "wal")  # type: ignore[arg-type]
    assert any("sqlite reports delete" in r.getMessage() for r in caplog.records)
    db.close()


def test_backup_of_wal_database_holds_unflushed_rows(tmp_path: Path) -> None:
    db = _make(tmp_path, journal_mode="wal")
    db.modify("INSERT INTO things(name) VALUES (?)", ("kept",))
    assert (tmp_path / "things_db.sqlite-wal").exists()
    assert db.backupdb("wal1")
    archive = tmp_path / "archive" / "things_db_wal1.sqlite.zip"
    with zipfile.ZipFile(archive) as zf:
        zf.extract("things_db_wal1.sqlite", tmp_path / "out")
    with sqlite3.connect(tmp_path / "out" / "things_db_wal1.sqlite") as conn:
        assert conn.execute("SELECT name FROM things").fetchall() == [("kept",)]
    conn.close()
    db.close()
