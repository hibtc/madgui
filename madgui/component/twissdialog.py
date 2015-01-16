"""
Dialog to set TWISS parameters.
"""

# force new style imports
from __future__ import absolute_import

from functools import partial

# internal
from madgui.core import wx
from madgui.widget.listview import ListView
from madgui.widget.input import ModalDialog
from madgui.widget.param import ParamDialog, Bool, String, Float, Matrix

from wx.lib.mixins.listctrl import CheckListCtrlMixin


__all__ = ['TwissDialog']


class ListCtrl(ListView, CheckListCtrlMixin):

    def __init__(self, *args, **kwargs):
        ListView.__init__(self, *args, **kwargs)
        CheckListCtrlMixin.__init__(self)
        self._OnCheckItem = lambda index, flag: None

    def OnCheckItem(self, index, flag):
        self._OnCheckItem(index, flag)


class ManageTwissDialog(ModalDialog):

    """
    Dialog to manage TWISS initial conditions.
    """

    def SetData(self, segman, data=None, inactive=None):
        self.segman = segman
        if data is None:
            self.data = segman.twiss_initial
        else:
            self.data = data
        if inactive is None:
            model = segman.simulator.model
            if model:
                self.inactive = {}    # TODO: use model's initial conditions
            else:
                self.inactive = {}
        else:
            self.inactive = inactive
        self._rows = []
        self.elements = segman.sequence.elements
        self._inserting = False

    def CreateContentArea(self):
        """Create sizer with content area, i.e. input fields."""
        content = wx.BoxSizer(wx.VERTICAL)
        self.InsertInputArea(content)
        self.InsertAddFieldArea(content)
        return content

    def InsertInputArea(self, outer):

        grid = ListCtrl(self, style=wx.LC_REPORT|wx.LC_SINGLE_SEL)
        grid._OnCheckItem = self.OnChangeActive
        grid.SetMinSize(wx.Size(400, 200))
        self._grid = grid
        # TODO: columns = use, at, element, data
        grid.InsertColumn(0, "Name", width=wx.LIST_AUTOSIZE)
        grid.InsertColumn(1, "Type")
        grid.InsertColumn(2, "s [m]", format=wx.LIST_FORMAT_RIGHT)
        headline = wx.StaticText(self, label="List of initial conditions:")

        button_edit = wx.Button(self, wx.ID_EDIT)
        button_remove = wx.Button(self, wx.ID_REMOVE)

        buttons = wx.BoxSizer(wx.VERTICAL)
        buttons.Add(button_edit, flag=wx.ALL|wx.EXPAND, border=5)
        buttons.AddSpacer(10)
        buttons.Add(button_remove, flag=wx.ALL|wx.EXPAND, border=5)

        inner = wx.BoxSizer(wx.HORIZONTAL)
        inner.Add(grid, 1, flag=wx.ALL|wx.EXPAND, border=5)
        inner.Add(buttons, flag=wx.ALL|wx.EXPAND, border=5)

        outer.Add(headline, flag=wx.ALL|wx.ALIGN_LEFT, border=5)
        outer.Add(inner, 1, flag=wx.ALL|wx.EXPAND, border=5)

        self.Bind(wx.EVT_BUTTON, self.OnButtonEdit, source=button_edit)
        self.Bind(wx.EVT_BUTTON, self.OnButtonRemove, source=button_remove)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateButton, source=button_edit)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateButton, source=button_remove)
        grid.Bind(wx.EVT_LEFT_DCLICK, self.OnDoubleClick)

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

    def OnDoubleClick(self, event):
        x, y = event.GetPosition()
        row, col = self._grid.GetCellId(x, y)
        self.EditTwiss(row)

    def OnChangeActive(self, row, active):
        if self._inserting:
            return
        index, _, twiss = self._rows[row]
        self._rows[row] = index, active, twiss

    def TransferDataToWindow(self):
        """Update dialog with initial values."""
        for index in sorted(self.data):
            self.AddTwissRow(index, self.data[index], True)
        for index in sorted(self.inactive):
            for twiss in self.inactive[index]:
                self.AddTwissRow(index, twiss, False)

    def TransferDataFromWindow(self):
        """Extract current active initial conditions."""
        data = {}
        inactive = {}
        for index, active, twiss in self._rows:
            if active:
                # merge multiple active TWISS at same element
                data.setdefault(index, {}).update(twiss)
            else:
                inactive.setdefault(index, []).append(twiss)
        self.data = data
        self.inactive = inactive

    def GetInsertRow(self, element_index):
        """
        Get the row number of the next item for the specified element should
        be inserted.
        """
        # This assumes the rows are sorted by element index, which is valid
        # because this function is used to determine the insertion index.
        bigger = (i for i, (index, active, twiss) in enumerate(self._rows)
                  if index > element_index)
        return next(bigger, len(self._rows))

    def AddTwissRow(self, elem_index, twiss_init=None, active=True):

        """
        Add one row to the list of TWISS initial conditions.
        """

        # require some TWISS initial conditions to be set
        if twiss_init is None:
            utool = self.segman.simulator.utool
            twiss_init = TwissDialog.show_modal(self, utool, {})
            if twiss_init is None:
                return

        grid = self._grid

        # insert elements
        self._inserting = True
        offset = self.GetInsertRow(elem_index)
        element = self.elements[elem_index]
        grid.InsertStringItem(offset, element['name'])
        grid.SetStringItem(offset, 1, element['type'])
        grid.SetStringItem(offset, 2, str(element['at']))
        grid.CheckItem(offset, active)
        grid.SetColumnWidth(0, wx.LIST_AUTOSIZE)

        # update stored data
        self._rows.insert(elem_index, (elem_index, active, twiss_init))
        self._inserting = False

    def OnButtonRemove(self, event):
        """Remove the Row with the specified."""
        grid = self._grid
        row = grid.GetFirstSelected()
        grid.DeleteItem(row)
        del self._rows[row]

    def OnButtonEdit(self, event):
        """Edit the TWISS initial conditions at the specified element."""
        self.EditTwiss(self._grid.GetFirstSelected())

    def EditTwiss(self, row):
        index, active, twiss = self._rows[row]
        utool = self.segman.simulator.utool
        twiss = TwissDialog.show_modal(self, utool, twiss)
        if twiss is not None:
            self._rows[index] = (index, active, twiss)

    def OnUpdateButton(self, event):
        event.Enable(self._grid.GetSelectedItemCount() > 0)


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

        # This property is used only by MadGUI and defines whether the initial
        # conditions should be used as "mixin", i.e. for every parameter which
        # is not defined, the TWISS results of the preceding segment are used.
        # TODO: While it required much less work to add this parameter in this
        # dialog, it should really be handled by ManageTwissDialog instead:
        Bool(mixin=False),
    ]
