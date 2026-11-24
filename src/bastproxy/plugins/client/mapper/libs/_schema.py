# Project: bastproxy
# Filename: plugins/client/mapper/libs/_schema.py
#
# File Description: the map database schema
#
# By: Bast
"""Constants and table definitions for the map database (ADR-0021)."""

from typing import Any

DB_NAME = "map"
DB_VERSION = 1

# exits from anywhere, as in the MUSHclient mapper: portals and recall
ANYWHERE_UID = "*"
RECALL_UID = "**"
ANYWHERE_UIDS = (ANYWHERE_UID, RECALL_UID)

# the touid of an exit that has not been explored
UNKNOWN_UID = "-1"

# room flags that block the exits from anywhere
NOPORTAL_FLAG = "noportal"
NORECALL_FLAG = "norecall"

AREAS_SQL = """CREATE TABLE areas(
        uid TEXT NOT NULL PRIMARY KEY,
        name TEXT default '',
        flags TEXT default '[]',
        details TEXT default '{}'
    )"""

ROOMS_SQL = """CREATE TABLE rooms(
        uid TEXT NOT NULL PRIMARY KEY,
        name TEXT default '',
        area TEXT default '',
        terrain TEXT default '',
        x INTEGER default 0,
        y INTEGER default 0,
        z INTEGER default 0,
        flags TEXT default '[]',
        details TEXT default '{}'
    )"""

EXITS_SQL = """CREATE TABLE exits(
        exit_id INTEGER NOT NULL PRIMARY KEY autoincrement,
        fromuid TEXT NOT NULL,
        dir TEXT NOT NULL,
        touid TEXT NOT NULL default '-1',
        cost INTEGER NOT NULL default 1,
        requirement TEXT,
        UNIQUE(fromuid, dir)
    )"""

BOOKMARKS_SQL = """CREATE TABLE bookmarks(
        uid TEXT NOT NULL PRIMARY KEY,
        notes TEXT
    )"""

STORAGE_SQL = """CREATE TABLE storage(
        name TEXT NOT NULL PRIMARY KEY,
        data TEXT
    )"""

INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS rooms_area ON rooms(area)",
    "CREATE INDEX IF NOT EXISTS exits_touid ON exits(touid)",
)

TABLES: list[dict[str, Any]] = [
    {"name": "areas", "sql": AREAS_SQL},
    {"name": "rooms", "sql": ROOMS_SQL},
    {"name": "exits", "sql": EXITS_SQL, "keyfield": "exit_id"},
    {"name": "bookmarks", "sql": BOOKMARKS_SQL},
    {"name": "storage", "sql": STORAGE_SQL},
]
