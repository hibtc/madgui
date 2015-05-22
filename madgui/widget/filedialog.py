# encoding: utf-8
"""
Utilities for file dialogs.
"""

# force new style imports
from __future__ import absolute_import

# GUI components
from madgui.core import wx

# exported symbols
__all__ = [
    'make_wildcard',
    'make_wildcards',
    'path_with_ext',
    'SaveDialog',
    'OpenDialog',
]


def make_wildcard(title, *exts):
    """Create wildcard string from a single wildcard tuple."""
    return "{0} ({1})|{1}".format(title, ";".join(exts))


def make_wildcards(*wildcards):
    """Create wildcard string from multiple wildcard tuples."""
    return "|".join(make_wildcard(*w) for w in wildcards)


def path_with_ext(dialog, wildcards):
    """Append extension if necessary."""
    _, ext = os.path.splitext(dialog.GetPath())
    if not ext:
        ext = wildcards[dialog.GetFilterIndex()][1] # use first extension
        ext = ext[1:]                               # remove leading '*'
        if ext == '.*':
            return _
    return _ + ext


def SaveDialog(window, title, wildcards):
    return wx.FileDialog(window, title, wildcard=make_wildcards(*wildcards),
                         style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)


def OpenDialog(window, title, wildcards):
    return wx.FileDialog(window, title, wildcard=make_wildcards(*wildcards),
                         style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
