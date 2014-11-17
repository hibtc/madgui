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
    # For now, 'license' is retrieved by the 'site' module:
    info.SetLicence(str(license))
    info.AddDeveloper(madgui.__author__)
    wx.AboutBox(info, parent=parent)


def connect_menu(notebook, menubar):
    """Add menuitem for about dialog."""
    def OnClick(event):
        show_about_dialog(notebook)
    helpmenu = menubar.Menus[2][0]
    menuitem = helpmenu.Append(wx.ID_ANY, '&About', 'Show about dialog.')
    notebook.Bind(wx.EVT_MENU, OnClick, menuitem)

