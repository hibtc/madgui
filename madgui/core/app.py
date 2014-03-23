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
from madgui.util.plugin import hookcollection
from madgui.util.common import makedirs

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

    hook = hookcollection(
        'madgui.core.app', [
            'init'
        ])

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

        # create log directory
        if self.args['--log']:
            self.logfolder = self.args['--log']
        else:
            self.logfolder = os.path.join(os.path.expanduser('~'), '.madgui')
        makedirs(self.logfolder)

        # allow plugin components to create stuff (frame!)
        self.hook.init(self)

        # signal wxwidgets to enter the main loop
        return True
