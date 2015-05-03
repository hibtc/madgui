"""
Widgets to set TWISS parameters.
"""

# force new style imports
from __future__ import absolute_import

from collections import namedtuple

# internal
from madgui.core import wx
from madgui.widget.element import ElementWidget
from madgui.widget.listview import ListCtrl, ColumnInfo
from madgui.widget.input import Widget, Dialog, Cancellable
from madgui.widget.param import ParamTable, Bool, String, Float, Matrix
from madgui.util.unit import format_quantity

# exported symbols
__all__ = [
    'format_element',
    'ManageTwissWidget',
    'TwissWidget',
]


def format_element(index, element):
    """Create an informative string representing an element."""
    return '{1[name]}'.format(index, element)


ItemInfo = namedtuple('ItemInfo', ['index', 'element', 'active', 'twiss'])


def _format_row_element(index, item):
    return format_element(item.index, item.element)


def _format_row_at(index, item):
    return format_quantity(item.element['at'], '.3f')


def _format_row_use(index, item):
    return 'Yes' if item.active else 'No'


def _format_row_data(index, item):
    return ', '.join(k + '=' + format_quantity(v)
                     for k, v in item.twiss.items())


class ManageTwissWidget(Widget):

    """
    Widget to manage TWISS initial conditions.
    """

    Title = "Select TWISS initial conditions"

    column_info = [
        ColumnInfo('Element', _format_row_element),
        ColumnInfo('At', _format_row_at, wx.LIST_FORMAT_RIGHT),
        ColumnInfo('Use', _format_row_use, wx.LIST_FORMAT_CENTER),
        ColumnInfo('Data', _format_row_data),
    ]

    def __init__(self, window, utool, **kw):
        self.utool = utool
        super(ManageTwissWidget, self).__init__(window, **kw)

    def CreateControls(self, window):

        """Create sizer with content area, i.e. input fields."""

        grid = ListCtrl(window, self.column_info)
        grid.SetMinSize(wx.Size(400, 200))
        self._grid = grid
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

    @Cancellable
    def OnButtonAdd(self, event):
        """Add the selected group to the dialog."""
        window = self.Window
        elements = self.elements
        with Dialog(window) as dialog:
            selected = ElementWidget(dialog).Query(elements, [0])
        i_el = selected[0]
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
        elif col == 2:
            self.ToggleActive(row)
        else:
            self.EditTwiss(row)

    def ToggleActive(self, row):
        items = self._grid.items
        item = items[row]
        items[row] = item._replace(active=not item.active)
        self._grid.RefreshItem(row)

    def SetData(self, elements, data, inactive={}):
        """Update dialog with initial values."""
        self.elements = elements
        items = [ItemInfo(index, elements[index][1], True, data[index])
                 for index in sorted(data)]
        items += [ItemInfo(index, elements[index][1], False, twiss)
                  for index in sorted(inactive)
                  for twiss in inactive[index]]
        self._grid.items = items

    def GetData(self):
        """Extract current active initial conditions."""
        data = {}
        inactive = {}
        for item in self._grid.items:
            if item.active:
                # merge multiple active TWISS at same element
                data.setdefault(item.index, {}).update(item.twiss)
            else:
                inactive.setdefault(item.index, []).append(item.twiss)
        return data, inactive

    def GetInsertRow(self, element_index):
        """
        Get the row number of the next item for the specified element should
        be inserted.
        """
        # This assumes the rows are sorted by element index, which is valid
        # because this function is used to determine the insertion index.
        items = self._grid.items
        bigger = (i for i, item in enumerate(items)
                  if item.index > element_index)
        return next(bigger, len(items))

    @Cancellable
    def AddTwissRow(self, index, active=True, twiss=None):

        """
        Add one row to the list of TWISS initial conditions.
        """

        # require some TWISS initial conditions to be set
        if twiss is None:
            with Dialog(self.Window) as dialog:
                twiss = TwissWidget(dialog, utool=self.utool).Query({})

        # insert elements
        row = self.GetInsertRow(index)
        item = ItemInfo(index, self.elements[index][1], active, twiss)
        self._grid.items.insert(row, item)
        return row

    def OnButtonRemove(self, event):
        """Remove the selected row."""
        del self._grid.items[self._grid.GetFirstSelected()]

    def OnButtonEdit(self, event):
        """Edit the TWISS initial conditions at the specified element."""
        self.EditTwiss(self._grid.GetFirstSelected())

    @Cancellable
    def EditTwiss(self, row):
        item = self._grid.items[row]
        with Dialog(self.Window) as dialog:
            twiss = TwissWidget(dialog, utool=self.utool).Query(item.twiss)
        item.twiss.clear()
        item.twiss.update(twiss)
        self._grid.RefreshItem(row)

    @Cancellable
    def ChooseElement(self, row):
        old_item = self._grid.items[row]
        elements = self.elements
        selected = [old_item.index]
        with Dialog(self.Window) as dialog:
            selected = ElementWidget(dialog).Query(elements, selected)
        new_index = selected[0]
        if new_index == old_item.index:
            return
        del self._grid.items[row]
        new_row = self.AddTwissRow(new_index, old_item.active, old_item.twiss)
        self._grid.Select(new_row)
        self._grid.Focus(new_row)

    def OnUpdateButton(self, event):
        event.Enable(self._grid.GetSelectedItemCount() > 0)


class TwissWidget(ParamTable):

    """
    Widget to show key-value pairs.
    """

    Title = "Set TWISS values"

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
