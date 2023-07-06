from typing import TypeVar, Protocol
import sys

from libs.commands import AddCommand, AddParser, AddArgument
from ._pluginhooks import RegisterPluginHook

Base = TypeVar('Base', bound='Base')

class Commands(Protocol):
    @RegisterPluginHook('post_initialize')
    def _phook_base_post_initialize_add_reset_command(self: Base): # pyright: ignore[reportInvalidTypeVarUse]
        """
        add commands to the plugin
        """
        if self.can_reset_f:
            self.api('plugins.core.commands:add.command.by.func')(self._command_reset, force=True)

    @AddCommand(group='Base')
    @AddParser(description='inspect a plugin')
    @AddArgument('-o',
                    '--object',
                    help='show an object of the plugin, can be method or variable',
                    default='')
    @AddArgument('-s',
                    '--simple',
                    help='show a simple output',
                    action='store_true')
    def _command_inspect(self: Base): # pyright: ignore[reportInvalidTypeVarUse]
        """
        show the plugin as it currently is in memory

        args dictionary:
          method - inspect specified method
          object - inspect specified object
                      to get to nested objects or dictionary keys use .
                      Ex. data.commands.stats.parser.description

          simple - only dump topllevel attributes
        """
        args = self.api('plugins.core.commands:get.current.command.args')()

        return True, self.api(f"{self.plugin_id}:dump")(args['object'], simple=args['simple'])[1]

    @AddCommand(group='Base')
    @AddParser(description='show plugin stats')
    def _command_stats(self: Base): # pyright: ignore[reportInvalidTypeVarUse]
        """
        @G%(name)s@w - @B%(cmdname)s@w
        show stats, memory, profile, etc.. for this plugin
        @CUsage@w: stats
        """
        stats = self._base_get_stats()
        tmsg = []
        for header in stats:
            tmsg.append(self.api('plugins.core.utils:center.colored.string')(header, '=', 60))
            tmsg.extend(
                f"{subtype:<20} : {stats[header][subtype]}"
                for subtype in stats[header]['showorder']
            )
        return True, tmsg

    @AddCommand(group='Base')
    @AddParser(description='show help info for this plugin')
    @AddArgument('-a',
                    '--api',
                    help='show functions this plugin has in the api',
                    action='store_true')
    @AddArgument('-c',
                    '--commands',
                    help='show commands in this plugin',
                    action='store_true')
    def _command_help(self: Base): # pyright: ignore[reportInvalidTypeVarUse]
        """
        @G%(name)s@w - @B%(cmdname)s@w
        show the help for this plugin
        @CUsage@w: help
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        width = 25

        msg = [
            f"{'Plugin ID':<{width}} : {self.plugin_id}",
            f"{'Name':<{width}} : {self.plugin_info.name}",
            f"{'Purpose':<{width}} : {self.plugin_info.purpose}",
            f"{'Author':<{width}} : {self.plugin_info.author}",
            f"{'Version':<{width}} : {self.plugin_info.version}",
            f"{'Package':<{width}} : {self.plugin_info.package}",
            f"{'Full Plugin Path':<{width}} : {self.plugin_info.full_package_path}",
            f"{'Time Loaded':<{width}} : {self.loaded_time.strftime(self.api.time_format)}",
        ]

        import_location = self.plugin_info.full_import_location

        if sys.modules[import_location].__doc__:
            msg.extend(sys.modules[import_location].__doc__.split('\n'))

        if msg[-1] == '' and msg[-2] == '':
            msg.pop()

        file_header = False
        for file in self.api('libs.pluginloader:plugin.get.changed.files')(self.plugin_id):
            if not file_header:
                file_header = True
                if msg[-1] != '':
                    msg.append('')
                msg.append(self.api('plugins.core.utils:center.colored.string')('@x86Files that have change since loading@w', '-', 60, filler_color='@B'))
            msg.append(f"    : {file}")
        if file_header:
            msg.append('@B' + '-' * 60 + '@w')

        file_header = False
        for file in self.api('libs.pluginloader:plugin.get.invalid.python.files')(self.plugin_id):
            if not file_header:
                file_header = True
                if msg[-1] != '':
                    msg.append('')
                msg.append(self.api('plugins.core.utils:center.colored.string')('@x86Files that are invalid python@w', '-', 60, filler_color='@B'))
            msg.append(f"    : {file}")
        if file_header:
            msg.append('@B' + '-' * 60 + '@w')

        if msg[-1] != '':
            msg.append('')

        if args['commands']:
            if cmd_list := self.api(
                'plugins.core.commands:get.commands.for.plugin.formatted'
            )(self.plugin_id):
                msg.extend(cmd_list)
                msg.extend(('@G' + '-' * 60 + '@w', ''))
        if args['api']:
            if api_list := self.api('libs.api:list')(self.plugin_id):
                msg.extend((f"API functions in {self.plugin_id}", '@G' + '-' * 60 + '@w'))
                msg.extend(api_list)
        return True, msg

    @AddCommand(group='Base')
    @AddParser(description='save the plugin state')
    def _command_save(self: Base): # pyright: ignore[reportInvalidTypeVarUse]
        """
        @G%(name)s@w - @B%(cmdname)s@w
        save plugin state
        @CUsage@w: save
        """
        self.api(f"{self.plugin_id}:save.state")()
        return True, ['Plugin settings saved']

    @AddCommand(group='Base', autoadd=False)
    @AddParser(description='reset the plugin')
    def _command_reset(self: Base): # pyright: ignore[reportInvalidTypeVarUse]
        """
        @G%(name)s@w - @B%(cmdname)s@w
          reset the plugin
          @CUsage@w: reset
        """
        if self.can_reset_f:
            self.api(f"{self.plugin_id}:reset")()
            return True, ['Plugin reset']

        return True, ['This plugin cannot be reset']

    @RegisterPluginHook('stats')
    def _phook_base_stats(self: Base, **kwargs): # pyright: ignore[reportInvalidTypeVarUse]
        """
        get statistics for commands
        """
        kwargs['stats']['Commands'] = {
            'Size': f"{sys.getsizeof(self.data['commands'])} bytes"
        }
        kwargs['stats']['Commands']['Number of Commands'] = len(self.data['commands'])
        kwargs['stats']['Commands']['showorder'] = ['Number of Commands', 'Size']

        return kwargs
