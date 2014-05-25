# encoding: utf-8
"""
Core application component.
"""

# force new style imports
from __future__ import absolute_import

# standard library
import os
import sys

# not so standard 3rdparty dependencies
import wx
import yaml

# internal
import madgui
from madgui.util.common import ivar, makedirs
from madgui.util.plugin import HookCollection

# exported symbols
__all__ = ['App']


def _load_config(filename):
    """Load a YAML configuration file."""
    if filename:
        with open(filename) as f:
            return yaml.safe_load(f)
    else:
        return {}


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
        config_file = args['--config']
        if config_file is None:
            config_file = os.path.join(os.path.expanduser('~'),
                                       '.madgui', 'config.yml')
            if os.path.exists(config_file):
                config_file = None
        conf = _load_config(config_file)
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
