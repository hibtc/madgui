# encoding: utf-8
"""
MadGUI core components.

This package provides the back-bone of MadGUI. When imported, it configures
matplotlib for use with a suitable version of wxWidgets.

To make sure that wxWidgets is initialized correctly, you should import this
module before importing :mod:`wx` or :mod:`matplotlib`. The best way to do
this is:

.. code:: python

    from madgui.core import wx, matplotlib
"""

# force new style imports
from __future__ import absolute_import

# standard library
import sys

# Make sure that the the following 'import wx' statement yields a suitable
# version of wxWidgets. This works only if 'wx' has not been imported yet.
# If it has been imported (assuming madgui is imported from another program),
# we will trust the user to have imported the correct version:
if 'wx' not in sys.modules:
    # If making a bundle with a tool like py2exe or PyInstaller then wxversion
    # must not be used, since it inspects the global, rather than the bundled
    # environment, the program will then simply fail. See:
    # http://www.wxpython.org/docs/api/wxversion-module.html
    if not hasattr(sys, 'frozen'):
        import wxversion
        wxversion.ensureMinimal('2.8')

# `wx` must be imported **after** wxversion.ensureMinimal
import wx

# use wxAgg as backend for matplotlib
import matplotlib
matplotlib.use('WXAgg')

# exported symbols:
__all__ = ['wx',
           'matplotlib']
