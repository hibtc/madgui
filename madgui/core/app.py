# encoding: utf-8
"""
Core application component.
"""

# force new style imports
from __future__ import absolute_import

# standard library
import os

# GUI components
import wx

# internal
import madgui
from madgui.util.common import ivar, makedirs
from madgui.util.plugin import HookCollection

# exported symbols
__all__ = ['App']


class App(wx.App):

    """
    Core application class.

    Use App.main() to run the application.

    :ivar args: command line arguments
    """

    version = madgui.__version__
    usage = madgui.__doc__

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
        cls(args).MainLoop()

    def __init__(self, args=None):
        """
        Create an application instance.

        :param dict args: preprocessed command line parameters
        """
        self.args = args
        super(App, self).__init__(redirect=False)

    def OnInit(self):

        """Initialize the application and create main window."""

        # allow plugin components to create stuff (frame!)
        self.hook.init(self)

        # signal wxwidgets to enter the main loop
        return True
