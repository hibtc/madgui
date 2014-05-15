# encoding: utf-8
"""
Dialog component to find/open a .madx file.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core import wx
from madgui.component.model import Model


def connect_menu(frame, menubar):
    def OnOpen(event):
        dlg = wx.FileDialog(frame,
                            style=wx.FD_OPEN,
                            wildcard="MADX files (*.madx;*.str)|*.madx;*.str|All files (*.*)|*")
        if dlg.ShowModal() == wx.ID_OK:
            _frame = frame.Claim()
            madx = _frame.vars['madx']
            madx.call(dlg.Path)
            # look for sequences
            sequences = madx.get_sequence_names()
            if len(sequences) == 0:
                # TODO: log
                name = None
            elif len(sequences) == 1:
                name = sequences[0]
            else:
                # if there are multiple sequences - just ask the user which
                # one to use rather than taking a wild guess based on twiss
                # computation etc
                dlg = wx.SingleChoiceDialog(parent=_frame,
                                            caption="Select sequence",
                                            message="Select sequence:",
                                            choices=sequences)
                if dlg.ShowModal() != wx.ID_OK:
                    return
                name = dlg.GetStringSelection()
            # now create the actual model object
            model = Model(madx, name=name)
            _frame.vars.update(control=model,
                               model=None,
                               name=name)
            if name:
                model.hook.show(model, _frame)
        dlg.Destroy()
    appmenu = menubar.Menus[0][0]
    menuitem = appmenu.Append(wx.ID_ANY, 'Load &MAD-X file\tCtrl+M')
    def OnUpdate(event):
        if frame.IsClaimed():
            menuitem.SetHelp('Open a .madx file in a new frame.')
        else:
            menuitem.SetHelp('Open a .madx file in this frame.')
        # skip the event, so more UpdateUI handlers can be invoked:
        event.Skip()
    frame.Bind(wx.EVT_MENU, OnOpen, menuitem)
    frame.Bind(wx.EVT_UPDATE_UI, OnUpdate, menubar)

