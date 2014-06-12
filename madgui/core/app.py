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

# not so standard 3rdparty dependencies
import wx

# internal
from madgui import __version__
from madgui.core.config import load_config
from madgui.core.plugin import HookCollection
from madgui.util.common import ivar

# exported symbols
__all__ = ['App']


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

    hook = ivar(HookCollection,
                init='madgui.core.app.init')

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
        self.args = args
        self.conf = conf
        super(App, self).__init__(redirect=False)

    def OnInit(self):
        """Initialize the application and create main window."""
        # allow plugin components to create stuff (frame!)
        self.hook.init(self)
        # signal wxwidgets to enter the main loop
        return True
