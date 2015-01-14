# encoding: utf-8
"""
About dialog that provides version and license information for the user.
"""

# force new style imports
from __future__ import absolute_import

# internal
import madgui
from madgui.core import wx


def show_about_dialog(parent):
    """Show the about dialog."""
    info = wx.AboutDialogInfo()
    info.SetName(madgui.__title__)
    info.SetVersion(madgui.__version__)
    info.SetDescription(madgui.__summary__)
    info.SetCopyright(madgui.__copyright__)
    info.SetWebSite(madgui.__uri__)
    info.SetLicence(madgui.get_license_text())
    info.AddDeveloper(madgui.__author__)
    try:
        wx.AboutBox(info, parent=parent)
    except TypeError:
        # 'parent' is not supported on windows (or just older wx version?):
        wx.AboutBox(info)
