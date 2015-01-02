# encoding: utf-8
"""
Dialog component to find/open a .madx file.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core import wx
from madgui.component.model import Segment


def connect_menu(frame, menubar):
    def OnOpen(event):
        dlg = wx.FileDialog(frame,
                            style=wx.FD_OPEN,
                            wildcard="MADX files (*.madx;*.str)|*.madx;*.str|All files (*.*)|*")
        if dlg.ShowModal() == wx.ID_OK:
            madx = frame.env['madx']
            madx.call(dlg.Path, True)
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
                dlg = wx.SingleChoiceDialog(parent=frame,
                                            caption="Select sequence",
                                            message="Select sequence:",
                                            choices=sequences)
                if dlg.ShowModal() != wx.ID_OK:
                    return
                name = dlg.GetStringSelection()
            # now create the actual model object
            model = Segment(madx, utool=frame.madx_units, name=name)
            frame.env.update(control=model,
                             model=None,
                             name=name)
            if name:
                model.hook.show(model, frame)
        dlg.Destroy()
    appmenu = menubar.Menus[0][0]
    menuitem = appmenu.Append(wx.ID_ANY, 'Load &MAD-X file\tCtrl+O',
                              'Open a .madx file in this frame.')
    frame.Bind(wx.EVT_MENU, OnOpen, menuitem)
