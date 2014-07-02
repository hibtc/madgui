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
    info.SetName('MadGUI')
    info.SetVersion(madgui.__version__)
    info.SetDescription("MadGUI is a python GUI for accelerator simulations using MAD-X.")
    info.SetCopyright('(C) 2013 - 2014 HIT Betriebs GmbH')
    info.SetWebSite('http://github.com/coldfix/madgui')
    # For now, 'license' is retrieved by the 'site' module:
    info.SetLicence(str(license))
    info.AddDeveloper('Thomas Gläßle')
    wx.AboutBox(info, parent=parent)


def connect_menu(notebook, menubar):
    """Add menuitem for about dialog."""
    def OnClick(event):
        show_about_dialog(notebook)
    helpmenu = menubar.Menus[2][0]
    menuitem = helpmenu.Append(wx.ID_ANY, '&About', 'Show about dialog.')
    notebook.Bind(wx.EVT_MENU, OnClick, menuitem)

