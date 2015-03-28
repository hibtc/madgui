"""
Widgets for element selection.
"""

# force new style imports
from __future__ import absolute_import

# GUI components
from madgui.core import wx
from madgui.widget.input import Widget
from madgui.widget import listview

from madgui.util.unit import strip_unit, units, format_quantity

# exported symbols
__all__ = [
    'ElementListWidget',
    'ElementWidget',
]


def _compile_element_searchtoken(search):

    """
    Prepare a match function for a given textual search string.

    Supports matching by name/type/index/position.
    """

    matchers = []               # match functions for a single property each
    search = search.lower()     # everything is lower-case in MAD-X

    # search string is an integer, so we can match the index
    try:
        num_i = int(search)
    except ValueError:
        pass
    else:
        def match_index(i, el):
            return i == num_i
        matchers.append(match_index)

    # search string is a float, so we can match the position
    try:
        num_f = float(search)
    except ValueError:
        pass
    else:
        meter = units.m
        def match_at(i, el):
            at = strip_unit(el['at'], meter)
            return (str(at).startswith(search)
                    or num_f >= at and num_f <= strip_unit(el['l'], meter))
        matchers.append(match_at)

    def match_type(i, el):
        return search in el['type']

    def match_name(i, el):
        return search in el['name']

    matchers.append(match_type)
    matchers.append(match_name)

    def match(i, el):
        return any(match(i, el) for match in matchers)

    return match


def filter_elements(elements, search):
    """
    Filter the list of elements using the given search string.

    Searches by name/type/index/position.
    """
    match = _compile_element_searchtoken(search)
    return [(i, el) for i, el in elements
            if match(i, el)]


class ElementListWidget(Widget):

    """
    ListCtrl widget that displays elements.

    Member variables:

    :ivar list elements: list of (id, element) of shown elements
    :ivar list selected: list of ids of selected elements
    """

    def Init(self, elements, selected):
        """Initialize data."""
        self.elements = elements
        self.selected = selected

    def GetColumns(self):
        """Column info for the ListCtrl."""
        return [
            listview.ColumnInfo(
                '',
                lambda _, item: item[0],
                wx.LIST_FORMAT_RIGHT,
                35),
            listview.ColumnInfo(
                'Name',
                lambda _, item: item[1]['name'],
                wx.LIST_FORMAT_LEFT,
                wx.LIST_AUTOSIZE),
            listview.ColumnInfo(
                'Type',
                lambda _, item: item[1]['type'],
                wx.LIST_FORMAT_LEFT,
                wx.LIST_AUTOSIZE),
            listview.ColumnInfo(
                'At',
                lambda _, item: format_quantity(item[1]['at'], '.3f'),
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
        ]

    def CreateControls(self):
        """Create element list and search controls."""
        listctrl = listview.ManagedListCtrl(self.GetWindow(),
                                            self.GetColumns())
        listctrl.setResizeColumn(2)
        listctrl.SetMinSize(wx.Size(400, 200))
        listctrl.Bind(wx.EVT_CHAR, self.OnChar)
        listctrl.Bind(wx.EVT_LEFT_DCLICK, self.OnDoubleClick)
        self._listctrl = listctrl
        return listctrl

    def OnChar(self, event):
        """Apply dialog when pressing Enter."""
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_RETURN:
            self.ApplyDialog()
        else:
            event.Skip()

    def OnDoubleClick(self, event):
        """Apply dialog when double clicking on list item."""
        x, y = event.GetPosition()
        row, col = self._listctrl.GetCellId(x, y)
        if row >= 0:
            self.ApplyDialog()
        else:
            event.Skip()

    def Validate(self, parent):
        """Check input validity."""
        return (self._listctrl.GetItemCount() > 0 and
                self._listctrl.GetSelectedItemCount() == 1)

    def TransferToWindow(self):
        """Update element list and selection."""
        self._listctrl.items = self.elements[:]
        selected = [_i for _i, (i, el) in enumerate(self.elements)
                    if i in self.selected]
        for i in selected:
            self._listctrl.Select(i)
            self._listctrl.Focus(i)

    def TransferFromWindow(self):
        """Retrieve the index of the selected element."""
        self.selected[:] = [i for i, el in self._listctrl.selected_items]


class ElementWidget(Widget):

    """Element selection dialog with a list control and a search box."""

    title = "Choose element"

    def Init(self, elements, selected):
        """Initialize data."""
        self.elements = elements
        self.selected = selected
        self._widget_elements = []
        self._widget_selected = []

    def CreateControls(self):
        """Create element list and search controls."""
        window = self.GetWindow()
        # create list control
        listctrl = self.CreateListCtrl()
        # create search control
        search_label = wx.StaticText(window, label="Search:")
        search_edit = wx.TextCtrl(window, style=wx.TE_RICH2)
        search_edit.SetFocus()
        # setup sizers
        search = wx.BoxSizer(wx.HORIZONTAL)
        search.Add(search_label, flag=wx.ALL|wx.ALIGN_CENTER, border=5)
        search.Add(search_edit, flag=wx.ALL|wx.ALIGN_CENTER, border=5)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(search, flag=wx.ALL|wx.ALIGN_RIGHT, border=5)
        sizer.Add(listctrl, 1, flag=wx.ALL|wx.EXPAND, border=5)
        # setup event handlers
        window.Bind(wx.EVT_TEXT, self.OnSearchChange, search_edit)
        # set member variables
        self._search = search_edit
        return sizer

    def _ListWidget(self, elements, selected):
        widget = ElementListWidget(elements=elements, selected=selected)
        widget.SetWindow(self.GetWindow())
        control = widget.CreateControls()
        return widget, control

    def CreateListCtrl(self):
        self._listwidget, self._listctrl = self._ListWidget(
            self._widget_elements,
            self._widget_selected)
        return self._listctrl

    def OnSearchChange(self, event):
        """Update element list."""
        self.TransferFromWindow()   # retrieve selected index
        self.TransferToWindow()     # filter by search string

    def TransferToWindow(self):
        """Update element list and selection."""
        searchtext = self._search.GetValue()
        filtered = filter_elements(self.elements, searchtext)
        self._widget_elements[:] = filtered
        self._widget_selected[:] = self.selected
        self._listwidget.TransferToWindow()

    def TransferFromWindow(self):
        """Retrieve the index of the selected element."""
        self._listwidget.TransferFromWindow()
        self.selected[:] = self._widget_selected

    def Validate(self, parent):
        return self._listwidget.Validate(parent)
