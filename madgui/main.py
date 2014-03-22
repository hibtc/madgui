"""
MadGUI - Interactive GUI cpymad.

Usage:
    madgui [-l <logs>]
    madgui (--help | --version)

Options:
    -l <logs>, --log=<logs>     Set log directory (default is '~/.madgui')
    -h, --help                  Show this help
    -v, --version               Show version information

"""
from __future__ import absolute_import

# wxpython
import wxversion
wxversion.ensureMinimal('2.8')
import wx

# use wxAgg as backend for matplotlib:
import matplotlib
matplotlib.use('WXAgg')

# standard library
import os

# app components
from .plugin import hookcollection
from .common import makedirs


class App(wx.App):
    """
    Core application class.

    Use App.main() to run the application.

    :ivar argv: command line arguments

    """
    version = '0.2'
    usage = globals()['__doc__']

    hook = hookcollection(
        'madgui.app', [
            'init'
        ])

    @classmethod
    def main(cls, argv=None):
        """
        Create an application instance and run the MainLoop.

        :param list argv: command line parameters, see App.usage for details.

        NOTE: The application instance is stored in the global name ``app``.

        """
        global app
        app = cls(argv)
        app.MainLoop()

    def __init__(self, argv=None):
        """
        Create an application instance.

        :param list argv: command line parameters, see App.usage for details.

        """
        self.argv = argv
        super(App, self).__init__(redirect=False)

    def OnInit(self):
        """
        Initialize the application.

        Parse the command line parameters and create the main frame.

        """
        # parse command line
        from docopt import docopt
        args = docopt(self.usage, self.argv, version=self.version)
        # create log directory
        if args['--log']:
            self.logfolder = args['--log']
        else:
            self.logfolder = os.path.join(os.path.expanduser('~'), '.madgui')
        makedirs(self.logfolder)
        self.hook.init(self)
        # signal wxwidgets to enter the main loop
        return True

if __name__ == '__main__':
    App.main()
