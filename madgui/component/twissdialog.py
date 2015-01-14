"""
Dialog to set TWISS parameters.
"""

# force new style imports
from __future__ import absolute_import

import bisect
from functools import partial

# internal
from madgui.core import wx
from madgui.widget.input import ModalDialog
from madgui.widget.param import ParamDialog, Bool, String, Float, Matrix


__all__ = ['TwissDialog']


def DestroyItem(sizer, index):
    """Remove item from sizer and destroy window."""
    window = sizer.Children[index].Window
    sizer.Remove(index)
    window.Destroy()


class ManageTwissDialog(ModalDialog):

    """
    Dialog to manage TWISS initial conditions.
    """

    def SetData(self, segman):
        self.segman = segman
        self._data = segman.twiss_initial
        self.data = {}
        self.elements = segman.sequence.elements

    def CreateContentArea(self):
        """Create sizer with content area, i.e. input fields."""
        content = wx.BoxSizer(wx.VERTICAL)
        self.InsertInputArea(content)
        self.InsertAddFieldArea(content)
        return content

    def InsertInputArea(self, outer):
        grid = wx.FlexGridSizer(rows=0, cols=4, vgap=5, hgap=5)
        grid.SetFlexibleDirection(wx.HORIZONTAL)
        grid.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_NONE) # fixed height
        headline = wx.StaticText(self, label="List of initial conditions:")
        outer.Add(headline, flag=wx.ALL|wx.ALIGN_LEFT, border=5)
        outer.Add(grid, flag=wx.ALL|wx.EXPAND, border=5)
        self._grid = grid
        self._headline = headline

    def InsertAddFieldArea(self, outer):
        """Create 'Add parameter' control."""
        sizer_add = wx.BoxSizer(wx.HORIZONTAL)
        self._ctrl_add = wx.Choice(self)
        self._ctrl_add.SetItems([
            elem['name']
            for elem in self.elements])
        for i in range(len(self.elements)):
            self._ctrl_add.SetClientData(i, i)
        self._ctrl_add.SetSelection(0)
        button_add = wx.Button(self, wx.ID_ADD)
        self.Bind(wx.EVT_BUTTON, self.OnButtonAdd, source=button_add)
        self.Bind(wx.EVT_UPDATE_UI, self.OnButtonAddUpdate, source=button_add)
        ins_flag = dict(flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL, border=5)
        sizer_add.Add(self._ctrl_add, **ins_flag)
        sizer_add.Add(button_add, **ins_flag)
        outer.AddSpacer(10)
        outer.Add(sizer_add, flag=wx.ALIGN_CENTER_HORIZONTAL)

    def OnButtonAdd(self, event):
        """Add the selected group to the dialog."""
        index = self._ctrl_add.GetSelection()
        i_el = self._ctrl_add.GetClientData(index)
        self.AddTwissRow(i_el)
        self.Layout()
        self.Fit()

    def OnButtonAddUpdate(self, event):
        event.Enable(self._ctrl_add.GetCount() > 0)

    def TransferDataToWindow(self):
        """
        Update dialog with initial values.
        """
        for index in sorted(self._data):
            self.AddTwissRow(index, self._data[index])

    def TransferDataFromWindow(self):
        """Not neeeded since data is saved on the fly."""
        pass

    def GetElementRow(self, element_index):
        """
        Get the row within the GridBagSizer in which the TWISS initial
        conditions for the element with the specified index are stored.
        """
        return bisect.bisect_left(sorted(self.data), element_index)

    def AddTwissRow(self, elem_index, twiss_init=None):

        """
        Add one row to the list of TWISS initial conditions.
        """

        # require some TWISS initial conditions to be set
        if twiss_init is None:
            utool = self.segman.simulator.utool
            twiss_init = TwissDialog.show_modal(self, utool, {})
            if twiss_init is None:
                return

        # on windows, this doesn't happen automatically, when adding
        # new items to the grid:
        grid = self._grid
        grid.SetRows(grid.GetRows() + 1)

        # insert elements
        offset = self.GetElementRow(elem_index) * grid.GetCols()
        element = self.elements[elem_index]
        txt_style = dict()
        btn_style = dict(style=wx.BU_EXACTFIT)
        ins_flag = dict(flag=wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT)
        label_at = wx.StaticText(self, label=str(element['at']), **txt_style)
        label_name = wx.StaticText(self, label=element['name'], **txt_style)
        button_edit = wx.Button(self, label="Edit", **btn_style)
        button_remove = wx.Button(self, label="Remove", **btn_style)
        grid.Insert(offset + 0, label_at, **ins_flag)
        grid.Insert(offset + 1, label_name, **ins_flag)
        grid.Insert(offset + 2, button_edit, **ins_flag)
        grid.Insert(offset + 3, button_remove, **ins_flag)
        self.Bind(wx.EVT_BUTTON,
                  partial(self.OnButtonEdit, elem_index),
                  source=button_edit)
        self.Bind(wx.EVT_BUTTON,
                  partial(self.OnButtonRemove, elem_index),
                  source=button_remove)

        # update stored data
        self.data[elem_index] = twiss_init

    def OnButtonRemove(self, elem_index, event):
        """Remove the Row with the specified."""
        grid = self._grid
        offset = self.GetElementRow(elem_index) * grid.GetCols()
        DestroyItem(grid, offset + 3)
        DestroyItem(grid, offset + 2)
        DestroyItem(grid, offset + 1)
        DestroyItem(grid, offset + 0)
        grid.SetRows(grid.GetRows() - 1)
        self.Layout()
        self.Fit()

    def OnButtonEdit(self, elem_index, event):
        """Edit the TWISS initial conditions at the specified element."""
        utool = self.segman.simulator.utool
        twiss_init = TwissDialog.show_modal(self, utool, self.data[elem_index])
        if twiss_init is not None:
            self.data[elem_index] = twiss_init


class TwissDialog(ParamDialog):

    """
    Dialog to show key-value pairs.
    """

    title = "Set TWISS values"

    # TODO:
    # - exclude more parameters (for most of these parameters, I actually
    #   don't know whether it makes sense to include them here)
    # - for excluded parameters show info string
    # - dynamically determine better default values
    params = [
        Float(betx=0, bety=0),
        Float(alfx=0, alfy=0),
        Float(mux=0, muy=0),
        Float(x=0, y=0),
        Float(t=0),
        Float(pt=0),
        Float(px=0, py=0),
        Float(dpx=0, dpy=0),
        Float(wx=0, wy=0),
        Float(phix=0, phiy=0),
        Float(dmux=0, dmuy=0),
        Float(ddx=0, ddy=0),
        Float(ddpx=0, ddpy=0),
        Matrix(r=[(0, 0),
                  (0, 0)]),
        Float(energy=0),
        Bool(chrom=True),
        String(file=""),
        String(save=""),
        String(table="twiss"),
        String(beta0=""),
        Matrix(re=[(1, 0, 0, 0, 0, 0),
                   (0, 1, 0, 0, 0, 0),
                   (0, 0, 1, 0, 0, 0),
                   (0, 0, 0, 1, 0, 0),
                   (0, 0, 0, 0, 1, 0),
                   (0, 0, 0, 0, 0, 1)]),
        Bool(centre=True),
        Bool(ripken=True),
        Bool(sectormap=True),
        String(sectortable=""),
        String(sectorfile="sectormap"),
        Bool(rmatrix=True),
        #String(sequence=""),   # line/sequence is passed by madgui
        #String(line=""),       # line/sequence is passed by madgui
        #String(range=""),      # range is passed by madgui
        String(useorbit=""),
        String(keeporbit=""),
        Float(tolerance=0),
        String(deltap=""),
        #Bool(notable=True),    # madgui always needs table
    ]
