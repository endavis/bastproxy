# Project: bastproxy
# Filename: plugins/core/records/_records.py
#
# File Description: a plugin to inspect records
#
# By: Bast

# Standard Library

from bastproxy.libs.logger import get_record_logs
from bastproxy.libs.records import RMANAGER
from bastproxy.libs.records.managers.records import DEFAULT_MAX_CHANGES, DEFAULT_MAX_TREES

# 3rd Party
# Project
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent

SHOW_LOG_SETTING = "showRecordLogs"
RETAINED_TREES_SETTING = "retained_trees"
MAX_CHANGES_SETTING = "tracking_max_changes"
CAPTURE_STACKS_SETTING = "capture_stacks"


def _format_record_logs(record_uuid: str) -> list[str]:
    """Format the log lines buffered for a record (not its descendants)."""
    lines = get_record_logs(record_uuid)
    return ["Log messages :", *[f"    {line}" for line in lines or ["none"]]]


class RecordPlugin(BasePlugin):
    """a plugin to inspect records."""

    @RegisterPluginHook("after_load")
    def _phook_initialize(self):
        """Initialize the instance."""
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            SHOW_LOG_SETTING,
            False,
            bool,
            "1 to show the log messages written while processing a record in the detail command",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            RETAINED_TREES_SETTING,
            DEFAULT_MAX_TREES,
            int,
            "number of root record trees kept in memory; older trees are evicted whole",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            MAX_CHANGES_SETTING,
            DEFAULT_MAX_CHANGES,
            int,
            "change entries each new record keeps",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            CAPTURE_STACKS_SETTING,
            False,
            bool,
            "capture the call stack of each new record and update, which costs time on every record; "
            "off by default",
        )
        self._apply_retained_trees(
            self.api("plugins.core.settings:setting.get")(self.plugin_id, RETAINED_TREES_SETTING)
        )
        self._apply_tracking_max_changes(
            self.api("plugins.core.settings:setting.get")(self.plugin_id, MAX_CHANGES_SETTING)
        )
        self._apply_capture_stacks(
            self.api("plugins.core.settings:setting.get")(self.plugin_id, CAPTURE_STACKS_SETTING)
        )

    def _apply_capture_stacks(self, value) -> None:
        """Write the capture_stacks setting onto the records manager."""
        if value is None:
            return
        RMANAGER.set_capture_stacks(bool(value))

    def _apply_retained_trees(self, value) -> None:
        """Write the retained_trees setting onto the records manager."""
        if value is None:
            return
        RMANAGER.set_max_trees(int(value))

    def _apply_tracking_max_changes(self, value) -> None:
        """Write the tracking_max_changes setting onto the records manager."""
        if value is None:
            return
        RMANAGER.set_max_changes(int(value))

    @RegisterToEvent(event_name="ev_{plugin_id}_var_retained_trees_modified")
    def _eventcb_retained_trees_modified(self):
        """Apply a changed retained_trees."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            self._apply_retained_trees(event_record["newvalue"])

    @RegisterToEvent(event_name="ev_{plugin_id}_var_tracking_max_changes_modified")
    def _eventcb_tracking_max_changes_modified(self):
        """Apply a changed tracking_max_changes."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            self._apply_tracking_max_changes(event_record["newvalue"])

    @RegisterToEvent(event_name="ev_{plugin_id}_var_capture_stacks_modified")
    def _eventcb_capture_stacks_modified(self):
        """Apply a changed capture_stacks."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            self._apply_capture_stacks(event_record["newvalue"])

    @AddParser(description="return the list of record types")
    def _command_types(self):
        """List the types of records."""
        tmsg = [
            f"Root trees: {RMANAGER.root_count()} (retaining {RMANAGER.max_trees})",
            "Record Types:",
        ]
        tmsg.extend(f"{rtype:<25} - {count}" for rtype, count in RMANAGER.get_types())
        return CommandResult(True, tmsg)

    @AddParser(description="get a list of a specific type of record")
    @AddArgument("recordtype", help="the type of record to list", default="")
    @AddArgument(
        "-c",
        "--count",
        help="the # of items to return (default 10)",
        default=10,
        nargs="?",
        type=int,
    )
    def _command_list(self):
        """List records of a specific type."""
        line_length = self.api("plugins.core.commands:output.line.length.get")()
        header_color = self.api("plugins.core.settings:setting.get")(
            "plugins.core.commands", "output_header_color"
        )

        args = self.api("plugins.core.commands:command.current.args.get")()
        rtypes = [rtype for rtype, _ in RMANAGER.get_types()]
        if not args["recordtype"] or args["recordtype"] not in rtypes:
            return CommandResult(True, ["Valid Types:", *[f"    {rtype}" for rtype in rtypes]])
        tmsg = [
            f"Last {args['count']} records of type {args['recordtype']}:",
            header_color + line_length * "-" + "@w",
        ]
        if records := RMANAGER.get_records(args["recordtype"], count=args["count"]):
            tmsg.extend([record.one_line_summary() for record in records])
        else:
            tmsg.append("No records found")

        return CommandResult(True, tmsg)

    @AddParser(description="get details of a specific record")
    @AddArgument("uid", help="the uid of the record", default="", nargs="?")
    @AddArgument("-u", "--update", help="the update uuid", default="")
    @AddArgument(
        "-dls",
        "--data_lines_to_show",
        help="the # of lines of data to show, -1 for all data",
        default=10,
        type=int,
    )
    @AddArgument(
        "-sd",
        "--show_data",
        help="show data in updates",
        action="store_false",
        default=True,
    )
    @AddArgument(
        "-ss",
        "--show_stack",
        help="show stack in updates",
        action="store_false",
        default=True,
    )
    @AddArgument(
        "-sfr",
        "--full_children_records",
        help="show the full children records (without updates)",
        action="store_true",
        default=False,
    )
    @AddArgument(
        "-iu",
        "--include_updates",
        help="include_updates in the detail",
        action="store_false",
        default=True,
    )
    @AddArgument(
        "-d",
        "--dump",
        help="dump the record to a file",
        action="store_true",
        default=False,
    )
    def _command_detail(self):
        """Get the details of a specific record."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        tmsg = []

        if not args["uid"]:
            tmsg.append("No record id provided")
            return CommandResult(True, tmsg)

        record = RMANAGER.get_record(args["uid"])

        # Records are list and can be empty, so check is None
        if record is None:
            tmsg.append(f"record {args['uid']} not found")

        elif args["update"]:
            if update := record.get_update(args["update"]):
                tmsg.extend(update.format_detailed())
            else:
                tmsg.append(f"update {args['update']} in record {args['uid']} not found")

        else:
            data = record.get_formatted_details(
                update_filter=[],
                full_children_records=args["full_children_records"],
                include_updates=args["include_updates"],
            )

            if self.api("plugins.core.settings:setting.get")(self.plugin_id, SHOW_LOG_SETTING):
                data = [*data, *_format_record_logs(record.uuid)]

            if args["dump"]:
                save_path = self.api.BASEDATAPATH / "dumps"
                save_path.mkdir(parents=True, exist_ok=True)
                file_path = save_path / f"{args['uid']}.txt"
                if file_path.exists():
                    file_path.unlink()
                with file_path.open("w") as f:
                    f.write("\n".join(data))

                tmsg.append(f"Record dumped to {file_path}")
            else:
                tmsg.extend(data)

        return CommandResult(True, tmsg)

    @AddParser(description="get a list of children of a specific record")
    @AddArgument("uid", help="the uid of the record", default="", nargs="?")
    def _command_children(self):
        """Get the children of a specific record."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        if not args["uid"]:
            return CommandResult(True, ["No record id provided"])

        record = RMANAGER.get_record(args["uid"])
        if not record:
            return CommandResult(True, [f"Record {args['uid']} not found"])

        child_records_formatted = RMANAGER.format_all_children(record)

        return CommandResult(True, child_records_formatted)
