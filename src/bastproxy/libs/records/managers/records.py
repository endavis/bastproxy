# Project: bastproxy
# Filename: libs/records/managers/records.py
#
# File Description: a manager that handles records of all types
#
# By: Bast
"""This module holds a manager that handles records of all types."""

# Standard Library
import itertools
from collections import deque
from typing import Any

# 3rd Party
# Project
from bastproxy.libs.api import API as BASEAPI
from bastproxy.libs.context import active_records
from bastproxy.libs.logger import get_logger

logger = get_logger(__name__)

# Root record trees kept before the oldest are evicted whole.
DEFAULT_MAX_TREES = 100
# Change entries each new record keeps.
DEFAULT_MAX_CHANGES = 1000
# Parentless data holders (pending records) kept before the oldest are evicted. Only an
# orphan that nothing ever adopts reaches this.
MAX_PENDING = 1000


_CREATION_SEQUENCE = itertools.count()


def next_creation_sequence() -> int:
    """Return the next process-wide creation sequence number.

    Timestamps can tie when the clock is coarse (Windows), so records and updates break
    ties on this number to keep creation order (#320).
    """
    return next(_CREATION_SEQUENCE)


class RecordManager:
    """Manager for tracking and storing records of various types.

    This class manages a collection of records, maintains an active record
    stack, and provides functionality for filtering and querying records.

    """

    def __init__(self):
        """Keep the last max_trees root record trees and track the active record.

        ``records`` maps a class name to its records by uuid, oldest first.
        """
        self.max_trees: int = DEFAULT_MAX_TREES
        self.max_changes: int = DEFAULT_MAX_CHANGES
        self.capture_stacks: bool = False
        self.records: dict[str, dict[str, Any]] = {}
        self.api = BASEAPI(owner_id="libs.records.managers.records")
        self.record_instances: dict[str, Any] = {}
        self._roots_since_prune: int = 0

    def set_max_trees(self, value: int) -> None:
        """Set how many root record trees are kept, then prune.

        Args:
            value: The number of trees. Below 1 logs a warning and uses 1.

        """
        trees = int(value)
        if trees < 1:
            logger.warning("retained trees %s is below 1, using 1", trees)
            trees = 1
        self.max_trees = trees
        self.prune()

    def set_max_changes(self, value: int) -> None:
        """Set the change entries each new record keeps.

        Records that already exist keep their cap.

        Args:
            value: The cap. Below 0 logs a warning and uses 0.

        """
        changes = int(value)
        if changes < 0:
            logger.warning("tracking max changes %s is negative, using 0", changes)
            changes = 0
        self.max_changes = changes

    def set_capture_stacks(self, value: bool) -> None:
        """Set whether new records capture call stacks.

        Records that already exist keep what they captured.

        Args:
            value: True to capture the call stack of each record and update.

        """
        self.capture_stacks = bool(value)

    def start(self, record):
        """Make ``record`` the innermost active record in the current context.

        Args:
            record: The record to mark as active.

        """
        active_records.set((*active_records.get(), record))

    def end(self, record):
        """Remove ``record`` from the active records of the current context.

        Call it in a ``finally`` after ``start``, from the same context.

        Args:
            record: The record to remove from the active records.

        """
        current = active_records.get()
        if not current or record != current[-1]:
            logger.warning(
                "RecordManger end: Record %s is not the same as the active record %s",
                record,
                current[-1] if current else None,
            )
        # remove the innermost occurrence, which is the last one
        remaining = list(current)
        for index in range(len(remaining) - 1, -1, -1):
            if remaining[index] == record:
                del remaining[index]
                break
        active_records.set(tuple(remaining))
        if not remaining and self._roots_since_prune >= max(1, self.max_trees // 10):
            self.prune()

    def get_latest_record(self):
        """Get the innermost active record.

        Returns:
            The most recently started record, or None if no record is executing.

        """
        records = active_records.get()
        return records[-1] if records else None

    def get_children(self, record, record_filter=None):
        """Get all direct children of a record.

        Args:
            record: The parent record to find children for.
            record_filter: Optional list of record types to exclude.

        Returns:
            A list of child records.

        """
        if not record_filter:
            record_filter = []
        rfilter = list(record_filter)
        return list(
            {
                rec
                for rec in self.record_instances.values()
                for parent in rec.parents
                if parent.uuid == record.uuid and rec.__class__.__name__ not in rfilter
            }
        )

    def get_all_children_dict(self, record, record_filter=None):
        """Get all children recursively as a nested dictionary.

        Args:
            record: The parent record to find children for.
            record_filter: Optional list of record types to exclude.

        Returns:
            A nested dictionary of records and their children.

        """
        if not record_filter:
            record_filter = []
        rfilter = list(record_filter)
        children = self.get_children(record, record_filter)
        children.sort()
        return {
            child: self.get_all_children_dict(child, rfilter)
            for child in children
            if child.__class__.__name__ not in rfilter
        }

    def get_all_children_list(self, record, record_filter=None):
        """Get all children recursively as a flat list.

        Args:
            record: The parent record to find children for.
            record_filter: Optional list of record types to exclude.

        Returns:
            A flat list of all descendant records.

        """
        if not record_filter:
            record_filter = []
        children = self.get_all_children_dict(record, record_filter)
        return self.api("plugins.core.utils:dict.key.list")(children)

    def format_all_children(self, record, record_filter=None):
        """Format all children as a tree structure with indentation.

        Args:
            record: The parent record to format children for.
            record_filter: Optional list of record types to exclude.

        Returns:
            A list of formatted strings showing the record tree.

        """
        if not record_filter:
            record_filter = []
        rfilter = list(record_filter)
        children = self.get_all_children_dict(record, rfilter)
        return [
            f"{'       ' * 0}{record.one_line_summary()}",
            *self.format_all_children_helper(children, record_filter=rfilter),
        ]

    def format_all_children_helper(
        self, children, indent=0, emptybar=None, output=None, record_filter=None
    ):
        """Helper method to recursively format children with proper indentation.

        Args:
            children: Dictionary of child records to format.
            indent: Current indentation level (default: 0).
            emptybar: Dictionary tracking which indent levels are empty.
            output: List to append formatted lines to.
            record_filter: Optional list of record types to exclude.

        Returns:
            A list of formatted strings with proper tree indentation.

        """
        if not emptybar:
            emptybar = {}
        emptybar[indent] = False
        if not record_filter:
            record_filter = []
        rfilter = list(record_filter)
        output = output or []
        all_children = list(children.keys())
        pre_string = "".join("    " if emptybar[i] else " |  " for i in range(indent))
        for child in children:
            all_children.pop(all_children.index(child))
            output.append(f"{pre_string} |-> {child.one_line_summary()}")
            if not all_children:
                emptybar[indent] = True
            self.format_all_children_helper(children[child], indent + 1, emptybar, output, rfilter)
        return output

    def add(self, record):
        """Add a record to the manager's tracking system.

        Args:
            record: The record to add.

        """
        queuename = record.__class__.__name__
        if record.uuid in self.record_instances:
            logger.error(
                "Record UUID collision %s already exists in the record manager", record.uuid
            )
        self.records.setdefault(queuename, {})[record.uuid] = record
        self.record_instances[record.uuid] = record
        if getattr(record, "retention_root", False) and not record.parents:
            self._roots_since_prune += 1

    def _is_root(self, record) -> bool:
        """Return True if the record starts a tree: a processing record with no parents."""
        return bool(getattr(record, "retention_root", False)) and not record.parents

    def root_count(self) -> int:
        """Count the root record trees currently stored."""
        return sum(1 for rec in self.record_instances.values() if self._is_root(rec))

    def _remove(self, record) -> None:
        """Remove a record from the stores. Its parents and children are left alone."""
        self.record_instances.pop(record.uuid, None)
        by_type = self.records.get(record.__class__.__name__)
        if by_type is not None:
            by_type.pop(record.uuid, None)

    def prune(self) -> None:
        """Evict the oldest root trees past ``max_trees``, each whole.

        A node shared with a tree that is kept survives, and so do the nodes below it.
        A root that is executing, or that has a record on the active stack below it, is
        kept. Parentless data holders are kept up to ``MAX_PENDING``. A failure is logged
        and never raised, because this runs from ``BaseRecord.__call__``.
        """
        self._roots_since_prune = 0
        try:
            self._prune()
        except Exception:
            logger.exception("RecordManager prune failed")

    def _prune(self) -> None:
        instances = self.record_instances
        children: dict[str, list[Any]] = {}
        roots: list[Any] = []
        pending: list[Any] = []
        dangling: list[Any] = []
        for rec in instances.values():
            parents = rec.parents
            if not parents:
                if getattr(rec, "retention_root", False):
                    roots.append(rec)
                else:
                    pending.append(rec)
                continue
            found = False
            for parent in parents:
                children.setdefault(parent.uuid, []).append(rec)
                if parent.uuid in instances:
                    found = True
            if not found:
                dangling.append(rec)

        protected: set[str] = set()
        active: set[str] = set()
        for rec in active_records.get():
            stack = [rec]
            while stack:
                node = stack.pop()
                if node.uuid in active:
                    continue
                active.add(node.uuid)
                if node.parents:
                    stack.extend(node.parents)
                elif node.uuid in instances:
                    protected.add(node.uuid)
        protected.update(r.uuid for r in roots if getattr(r, "executing", False))

        excess = [
            r for r in roots[: max(0, len(roots) - self.max_trees)] if r.uuid not in protected
        ]
        excess += pending[: max(0, len(pending) - MAX_PENDING)]
        excess += dangling
        if not excess:
            return

        doomed: dict[str, Any] = {}
        queue = deque(excess)
        while queue:
            node = queue.popleft()
            if node.uuid in doomed or node.uuid not in instances:
                continue
            doomed[node.uuid] = node
            queue.extend(children.get(node.uuid, ()))

        survivors: set[str] = set()
        queue = deque()
        for uid, node in doomed.items():
            kept_parent = any(p.uuid in instances and p.uuid not in doomed for p in node.parents)
            if kept_parent or uid in active:
                survivors.add(uid)
                queue.append(node)
        while queue:
            node = queue.popleft()
            for child in children.get(node.uuid, ()):
                if child.uuid in doomed and child.uuid not in survivors:
                    survivors.add(child.uuid)
                    queue.append(child)

        for uid, node in doomed.items():
            if uid not in survivors:
                self._remove(node)

    def get_types(self):
        """Get all record types and their counts.

        Returns:
            A list of tuples containing (record_type, count).

        """
        return [(key, len(self.records[key])) for key in self.records]

    def get_records(self, recordtype, count=10):
        """Get the last N records of a specific type.

        Args:
            recordtype: The type of records to retrieve.
            count: Number of records to retrieve (default: 10).

        Returns:
            A list of records, oldest first, or None if type doesn't exist.

        """
        records = self.records.get(recordtype, None)
        if records is None:
            return None
        values = list(records.values())
        return values[-count:] if count > 0 else []

    def get_record(self, recordid):
        """Get a specific record by its UUID.

        Args:
            recordid: The UUID of the record to retrieve.

        Returns:
            The record if found, None otherwise.

        """
        return self.record_instances.get(recordid, None)


RMANAGER = RecordManager()
