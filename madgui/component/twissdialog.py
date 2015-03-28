"""
Widgets to set TWISS parameters.
"""

# force new style imports
from __future__ import absolute_import

from functools import partial

# internal
from madgui.core import wx
from madgui.widget.element import ElementWidget
from madgui.widget.listview import CheckListCtrl
from madgui.widget.input import Widget
from madgui.widget.param import ParamTable, Bool, String, Float, Matrix
from madgui.util.unit import strip_unit, units, format_quantity

# exported symbols
__all__ = [
    'format_element',
    'ManageTwissWidget',
    'TwissWidget',
]


def format_element(index, element):
    """Create an informative string representing an element."""
    return '{1[name]}'.format(index, element)


class ManageTwissWidget(Widget):

    """
    Widget to manage TWISS initial conditions.
    """

    title = "Select TWISS initial conditions"

    def Init(self, segman, data=None, inactive=None):
        self.segman = segman
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
        self.elements = segman.elements
        self._inserting = False

    def CreateControls(self):

        """Create sizer with content area, i.e. input fields."""

        window = self.GetWindow()

        grid = CheckListCtrl(window, style=wx.LC_REPORT|wx.LC_SINGLE_SEL)
        grid._OnCheckItem = self.OnChangeActive
        grid.SetMinSize(wx.Size(400, 200))
        self._grid = grid
        # TODO: columns = use, at, element, data
        grid.InsertColumn(0, "Element", width=wx.LIST_AUTOSIZE)
        grid.InsertColumn(1, "At [m]", width=wx.LIST_AUTOSIZE)
        grid.InsertColumn(2, "Data", width=wx.LIST_AUTOSIZE)
        headline = wx.StaticText(window, label="List of initial conditions:")

        button_edit = wx.Button(window, wx.ID_EDIT)
        button_add = wx.Button(window, wx.ID_ADD)
        button_remove = wx.Button(window, wx.ID_REMOVE)

        buttons = wx.BoxSizer(wx.VERTICAL)
        buttons.Add(button_add, flag=wx.ALL|wx.EXPAND, border=5)
        buttons.Add(button_remove, flag=wx.ALL|wx.EXPAND, border=5)
        buttons.AddSpacer(10)
        buttons.Add(button_edit, flag=wx.ALL|wx.EXPAND, border=5)

        inner = wx.BoxSizer(wx.HORIZONTAL)
        inner.Add(grid, 1, flag=wx.ALL|wx.EXPAND, border=5)
        inner.Add(buttons, flag=wx.ALL|wx.EXPAND, border=5)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(headline, flag=wx.ALL|wx.ALIGN_LEFT, border=5)
        outer.Add(inner, 1, flag=wx.ALL|wx.EXPAND, border=5)

        window.Bind(wx.EVT_BUTTON, self.OnButtonEdit, source=button_edit)
        window.Bind(wx.EVT_BUTTON, self.OnButtonAdd, source=button_add)
        window.Bind(wx.EVT_BUTTON, self.OnButtonRemove, source=button_remove)
        window.Bind(wx.EVT_UPDATE_UI, self.OnUpdateButton, source=button_edit)
        window.Bind(wx.EVT_UPDATE_UI, self.OnUpdateButton, source=button_remove)
        grid.Bind(wx.EVT_LEFT_DCLICK, self.OnDoubleClick)

        return outer

    def OnButtonAdd(self, event):
        """Add the selected group to the dialog."""
        window = self.GetWindow()
        selected = [0]
        retcode = ElementWidget.ShowModal(window, elements=self.elements,
                                          selected=selected)
        if retcode != wx.ID_OK:
            return
        i_el = selected[0][0]
        # TODO: use the TWISS results at this element as default values for
        # the TwissWidget (?):
        self.AddTwissRow(i_el)
        window.Layout()
        window.Fit()

    def OnDoubleClick(self, event):
        x, y = event.GetPosition()
        row, col = self._grid.GetCellId(x, y)
        if row < 0:
            return
        if col == 0 or col == 1:
            self.ChooseElement(row)
        else:
            self.EditTwiss(row)

    def OnChangeActive(self, row, active):
        if self._inserting:
            return
        index, _, twiss = self._rows[row]
        self._rows[row] = index, active, twiss

    def TransferToWindow(self):
        """Update dialog with initial values."""
        for index in sorted(self.data):
            self.AddTwissRow(index, self.data[index], True)
        for index in sorted(self.inactive):
            for twiss in self.inactive[index]:
                self.AddTwissRow(index, twiss, False)

    def TransferFromWindow(self):
        """Extract current active initial conditions."""
        data = {}
        inactive = {}
        for index, active, twiss in self._rows:
            if active:
                # merge multiple active TWISS at same element
                data.setdefault(index, {}).update(twiss)
            else:
                inactive.setdefault(index, []).append(twiss)
        self.data.clear()
        self.data.update(data)
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
            twiss_init = {}
            utool = self.segman.simulator.utool
            retcode = TwissWidget.ShowModal(self.GetWindow(), utool=utool,
                                            data=twiss_init)
            if retcode != wx.ID_OK:
                return

        grid = self._grid

        # insert elements
        self._inserting = True
        offset = self.GetInsertRow(elem_index)
        element = self.elements[elem_index]
        at = strip_unit(element['at'], units.m)
        data_text = ', '.join(k + '=' + format_quantity(v)
                              for k, v in twiss_init.items())
        grid.InsertStringItem(offset, format_element(elem_index, element))
        grid.SetStringItem(offset, 1, '{:.3f}'.format(at))
        grid.SetStringItem(offset, 2, data_text)
        grid.CheckItem(offset, active)
        grid.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        grid.SetColumnWidth(1, wx.LIST_AUTOSIZE)
        grid.SetColumnWidth(2, wx.LIST_AUTOSIZE)

        # update stored data
        self._rows.insert(elem_index, (elem_index, active, twiss_init))
        self._inserting = False

        return offset

    def OnButtonRemove(self, event):
        """Remove the selected row."""
        self.RemoveRow(self._grid.GetFirstSelected())

    def RemoveRow(self, row):
        """Remove specified row."""
        self._grid.DeleteItem(row)
        del self._rows[row]

    def OnButtonEdit(self, event):
        """Edit the TWISS initial conditions at the specified element."""
        self.EditTwiss(self._grid.GetFirstSelected())

    def EditTwiss(self, row):
        index, active, twiss = self._rows[row]
        utool = self.segman.simulator.utool
        retcode = TwissWidget.ShowModal(self.GetWindow(), utool=utool,
                                        data=twiss)
        if retcode == wx.ID_OK:
            # TODO: update item
            pass

    def ChooseElement(self, row):
        old_element_index, active, twiss = self._rows[row]
        selected = [old_element_index]
        retcode = ElementWidget.ShowModal(window, elements=self.elements,
                                          selected=selected)
        if retcode != wx.ID_OK:
            return
        new_element_index = selected[0]
        if new_element_index == old_element_index:
            return
        self.RemoveRow(row)
        new_row = self.AddTwissRow(new_element_index, twiss, active)
        self._grid.Select(new_row)
        self._grid.Focus(new_row)

    def OnUpdateButton(self, event):
        event.Enable(self._grid.GetSelectedItemCount() > 0)


class TwissWidget(ParamTable):

    """
    Widget to show key-value pairs.
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
        # dialog, it should really be handled by ManageTwissWidget instead:
        Bool(mixin=False),
    ]
