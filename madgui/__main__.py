"""
Run the MadGUI application.

This module is invoked when calling ``python -m madgui``.

For more information on the command line parameters, see App.usage.

"""
from __future__ import absolute_import
from .main import App

if __name__ == '__main__':
    App.main()
