# encoding: utf-8
"""
Run the MadGUI application.

This module is invoked when calling ``python -m madgui``.

For more information on the command line parameters, see :attr:`App.usage`.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.app import App

# exported symbols
__all__ = []


if __name__ == '__main__':
    App.main()
