"""Regression guard for the sqldb and ssc API renames (#171)."""

from pathlib import Path

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.exceptions import APINotFoundError
from bastproxy.plugins.core.sqldb.libs._sqlite import Sqldb
from bastproxy.plugins.core.sqldb.plugin._sqldb import SQLDBPlugin
from bastproxy.plugins.core.ssc.plugin._ssc import SSC
from tests.plugins.test_api_name_grammar import (
    SRC,
    api_name_error,
    collect_registrations,
)

SQLDB = "plugins.core.sqldb"
SSC_OWNER = "plugins.core.ssc"

RENAMES: dict[tuple[str, str], str] = {
    (SQLDB, "{database_name}.get.single.row"): "{database_name}.row.get",
    (SQLDB, "baseclass"): "baseclass.get",
    (SSC_OWNER, "ssc.{name}"): "ssc.{name}.get",
}

CASES = sorted(RENAMES.items())

OLD_CALLER_NEEDLES = [
    'plugins.core.sqldb:baseclass"',
    ':ssc.proxypw"',
    ':ssc.proxypwview"',
    ':ssc.mudpw"',
    '.get.single.row"',
]


def _registered(api: API, name: str) -> bool:
    try:
        api.get(name)
    except APINotFoundError:
        return False
    return True


def test_three_renames() -> None:
    assert len(RENAMES) == 3


@pytest.mark.parametrize(("old", "new"), CASES)
def test_new_name_registered_and_old_gone(old: tuple[str, str], new: str) -> None:
    registrations = collect_registrations()[0]
    assert (old[0], new) in registrations
    assert old not in registrations


@pytest.mark.parametrize(("old", "new"), CASES)
def test_new_name_passes_grammar(old: tuple[str, str], new: str) -> None:
    assert api_name_error(new) is None


def test_no_source_calls_an_old_name() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text()
        offenders.extend(f"{path}: {n}" for n in OLD_CALLER_NEEDLES if n in text)
    assert offenders == []


def test_sqldb_object_registers_row_get(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toplevel = "tests.dyn171"
    db = Sqldb(toplevel, dbname="dyn171db", dbdir=tmp_path)
    sentinel = object()
    monkeypatch.setattr(db, "getrow", lambda row_id, table_name: sentinel)
    api = API(owner_id=toplevel)
    try:
        api("libs.api:api.add.for.object")(toplevel, db)
        assert _registered(api, f"{toplevel}:dyn171db.row.get")
        assert not _registered(api, f"{toplevel}:dyn171db.get.single.row")
        assert api(f"{toplevel}:dyn171db.row.get")(1, "tbl") is sentinel
    finally:
        api("libs.api:api.toplevel.remove")(toplevel)


def test_ssc_object_registers_name_get(tmp_path: Path) -> None:
    toplevel = "tests.dyn171ssc"
    ssc = SSC("dyn171pw", toplevel, tmp_path, default="d")
    api = API(owner_id=toplevel)
    try:
        api("libs.api:api.add.for.object")(toplevel, ssc)
        assert _registered(api, f"{toplevel}:ssc.dyn171pw.get")
        assert not _registered(api, f"{toplevel}:ssc.dyn171pw")
        getter = api(f"{toplevel}:ssc.dyn171pw.get")
        assert getter(quiet=True) == "d"
        (tmp_path / "dyn171pw").write_text("secret\n", encoding="utf-8")
        assert getter(quiet=True) == "secret"
    finally:
        api("libs.api:api.toplevel.remove")(toplevel)


def test_baseclass_get_returns_sqldb() -> None:
    assert SQLDBPlugin._api_baseclass_get(None) is Sqldb
