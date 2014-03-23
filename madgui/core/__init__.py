# encoding: utf-8
"""
GUI package containing some view components.

To make sure that wxwidgets is initialized correctly, you should always
import this module before importing :mod:`wx` or :mod:`matplotlib`. The
best way to do this is:

.. code:: python

    from madgui.gui import wx, matplotlib

The exception being the modules within this very package don't need to
adhere to this rule: The package setup code is always executed before the
module.
"""

# force new style imports
from __future__ import absolute_import

# ensure a minimal version of wxwidgets
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
