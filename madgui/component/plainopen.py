# encoding: utf-8
"""
Dialog component to find/open a model.
"""

# force new style imports
from __future__ import absolute_import

# 3rd party
from cern.cpymad.madx import Madx

# internal
from madgui.core import wx
from madgui.component.model import Model



def connect_menu(frame, menubar):
    def OnOpen(event):
        dlg = wx.FileDialog(frame,
                            style=wx.FD_OPEN,
                            wildcard="MADX files (*.madx;*.str)|*.madx;*.str|All files (*.*)|*")
        if dlg.ShowModal() == wx.ID_OK:
            name = dlg.Path
            madx = Madx()
            madx.call(name)
            model = Model(madx, name=name)
            _frame = frame.Reserve(madx=madx,
                                   control=model,
                                   model=None,
                                   name=name)
            # TODO: iterate all available sequences (if there is no active
            # sequence?) and ask the user which one to use.
            try:
                twiss = madx.get_active_sequence().twiss
            except (RuntimeError, ValueError):
                pass
            else:
                model.hook.show(model, _frame)
        dlg.Destroy()
    appmenu = menubar.Menus[0][0]
    menuitem = appmenu.Append(wx.ID_ANY,
                              'Load &MADX file\tCtrl+M',
                              'Load a plain MADX file without any metadata.')
    menubar.Bind(wx.EVT_MENU, OnOpen, menuitem)

