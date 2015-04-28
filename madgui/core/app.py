# encoding: utf-8
"""
MadGUI - interactive GUI application for MAD-X via cpymad.

Usage:
    madgui [--config <config>]
    madgui (--help | --version)

Options:
    --config=<config>       Set config file
    -h, --help              Show this help
    -v, --version           Show version information

Contact information:

    Thomas Gläßle <t_glaessle@gmx.de>

Website:

    https://github.com/coldfix/madgui
"""

# force new style imports
from __future__ import absolute_import

from pkg_resources import (EntryPoint, Requirement, working_set,
                           iter_entry_points)

# not so standard 3rdparty dependencies
import wx

# internal
from madgui import __version__
from madgui.core.config import load_config, recursive_merge
from madgui.core.plugin import HookCollection

# exported symbols
__all__ = [
    'App',
]


# Alias for later use inside App, where __doc__ means App.__doc__. There is no
# need to set _version here, but it looks much nicer:
_version = __version__
_usage = __doc__


class App(wx.App):

    """
    Core application class.

    Use App.main() to run the application.

    :ivar args: command line arguments
    """

    version = _version
    usage = _usage

    entry_points = """
        [madgui.core.app.init]
        mainframe = madgui.widget.notebook:NotebookFrame

        [madgui.widget.figure.init]
        matchtool = madgui.component.matchtool:MatchTool
        selecttool = madgui.component.selecttool:SelectTool
        comparetool = madgui.component.comparetool:CompareTool
        statusbar = madgui.component.lineview:UpdateStatusBar.create
        drawelements = madgui.component.lineview:DrawLineElements.create

        [madgui.component.matching.start]
        drawconstraints = madgui.component.lineview:DrawConstraints
    """

    @classmethod
    def main(cls, argv=None):
        """
        Create an application instance and run the MainLoop.

        :param list argv: command line parameters
        """
        from docopt import docopt
        args = docopt(cls.usage, argv, version=cls.version)
        conf = load_config(args['--config'])
        cls(args, conf).MainLoop()

    def __init__(self, args=None, conf=None):
        """
        Create an application instance.

        :param dict args: preprocessed command line parameters
        """
        self.hook = HookCollection(
            init='madgui.core.app.init')
        self.args = args
        self.conf = conf
        self.dist = working_set.find(Requirement.parse('madgui'))
        self.add_entry_points(self.entry_points)
        # Add all entry point maps (strings like `App.entry_point` above) that
        # are registered under 'madgui.entry_points'. This indirection renders
        # the plugin mechanism more dynamic and allows plugins to be defined
        # more easily by eliminating the need to execute 'setup.py' each time
        # an entrypoint is added, changed or removed. Instead, their setup
        # step only needs to create a single entrypoint which is less likely
        # to change.
        for ep in iter_entry_points('madgui.entry_points'):
            self.add_entry_points(ep.load())
        super(App, self).__init__(redirect=False)

    def OnInit(self):
        """Initialize the application and create main window."""
        # allow plugin components to create stuff (frame!)
        self.hook.init(self)
        # signal wxwidgets to enter the main loop
        return True

    def add_entry_points(self, entry_map_section):
        """Add entry points."""
        recursive_merge(
            self.dist.get_entry_map(),
            EntryPoint.parse_map(entry_map_section, self.dist))
