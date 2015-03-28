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
    return [(i, el) for i, el in enumerate(elements)
            if match(i, el)]


class ElementWidget(Widget):

    """Element selection dialog with a list control and a search box."""

    title = "Choose element"

    def Init(self, elements, selected):
        """Initialize data."""
        self.elements = list(elements)
        self.selected = selected

    def CreateControls(self):
        """Create element list and search controls."""
        window = self.GetWindow()
        # create list control
        listctrl = listview.ManagedListCtrl(window, [
            listview.ColumnInfo(
                '',
                lambda index, _: index,
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
        ])
        listctrl.setResizeColumn(2)
        listctrl.SetMinSize(wx.Size(400, 200))
        # create search control
        search_label = wx.StaticText(window, label="Search")
        search_edit = wx.TextCtrl(window, style=wx.TE_RICH2)
        search_edit.SetFocus()
        # setup sizers
        search = wx.BoxSizer(wx.HORIZONTAL)
        search.Add(search_label, flag=wx.ALL, border=5)
        search.Add(search_edit, flag=wx.ALL, border=5)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(search, flag=wx.ALL|wx.ALIGN_RIGHT, border=5)
        sizer.Add(listctrl, 1, flag=wx.ALL|wx.EXPAND, border=5)
        # setup event handlers
        window.Bind(wx.EVT_TEXT, self.OnSearchChange, search_edit)
        listctrl.Bind(wx.EVT_CHAR, self.OnChar)
        listctrl.Bind(wx.EVT_LEFT_DCLICK, self.OnDoubleClick)
        # set member variables
        self._listctrl = listctrl
        self._search = search_edit
        return sizer

    def OnSearchChange(self, event):
        """Update element list."""
        self.TransferToWindow()

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

    def TransferToWindow(self):
        """Update element list and selection."""
        searchtext = self._search.GetValue()
        filtered_elements = filter_elements(self.elements, searchtext)
        self._listctrl.items = filtered_elements
        try:
            sel_index = self.selected[0]
            sel_element = self.elements[sel_index]
            selected = filtered_elements.index((sel_index, sel_element))
        except (IndexError, ValueError):
            return
        self._listctrl.Select(selected)
        self._listctrl.Focus(selected)

    def TransferFromWindow(self):
        """Retrieve the index of the selected element."""
        self.selected[0] = self._listctrl.selected_items[0]

    def Validate(self, parent):
        """Check input validity."""
        return (self._listctrl.GetItemCount() > 0 and
                self._listctrl.GetSelectedItemCount() == 1)
