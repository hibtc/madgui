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
    'RangeListWidget',
    'RangeWidget',
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


def filter_elements(elements, search, keep=()):
    """
    Filter the list of elements using the given search string.

    Searches by name/type/index/position.
    """
    match = _compile_element_searchtoken(search)
    return [(i, el) for i, el in elements
            if i in keep or match(i, el)]


class ElementListWidget(Widget):

    """
    ListCtrl widget that displays elements.

    Member variables:

    :ivar list elements: list of (id, element) of shown elements
    :ivar list selected: list of ids of selected elements
    """

    Style = wx.LC_SINGLE_SEL

    column_info = [
        listview.ColumnInfo(
            '',
            lambda _, item: item[0],
            wx.LIST_FORMAT_RIGHT,
            35),
        listview.ColumnInfo(
            'Name',
            lambda _, item: item[1]['name'],
            wx.LIST_FORMAT_LEFT),
        listview.ColumnInfo(
            'Type',
            lambda _, item: item[1]['type'],
            wx.LIST_FORMAT_LEFT),
        listview.ColumnInfo(
            'At',
            lambda _, item: format_quantity(item[1]['at'], '.3f'),
            wx.LIST_FORMAT_RIGHT),
    ]

    def CreateControls(self, window):
        """Create element list and search controls."""
        listctrl = listview.ListCtrl(window,
                                     self.column_info,
                                     style=self.Style)
        listctrl.setResizeColumn(2)
        listctrl.SetMinSize(wx.Size(400, 200))
        listctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnActivateItem)
        self._listctrl = listctrl
        return listctrl

    def OnActivateItem(self, event):
        """Apply dialog when pressing Enter."""
        self.ApplyDialog()

    def Validate(self, parent):
        """Check input validity."""
        return (self._listctrl.GetItemCount() > 0 and
                self._listctrl.GetSelectedItemCount() == 1)

    def SetData(self, elements, selected):
        """Update element list and selection."""
        self._listctrl.items = elements
        selected = [_i for _i, (i, el) in enumerate(elements)
                    if i in selected]
        for i in selected:
            self._listctrl.Select(i)
            self._listctrl.Focus(i)

    def GetData(self):
        """Retrieve the index of the selected element."""
        return [i for i, el in self._listctrl.selected_items]


class ElementWidget(Widget):

    """Element selection dialog with a list control and a search box."""

    Title = "Choose element"
    ListWidget = ElementListWidget
    label = 'Select element:'

    def CreateControls(self, window):
        """Create element list and search controls."""
        # create list control
        listctrl = self.CreateListCtrl()
        # create search control
        self.ctrl_label = label = wx.StaticText(window, label=self.label)
        search_label = wx.StaticText(window, label="Search:")
        search_edit = wx.TextCtrl(window, style=wx.TE_RICH2)
        search_edit.SetFocus()
        # setup sizers
        search = wx.BoxSizer(wx.HORIZONTAL)
        search.Add(label, flag=wx.ALL|wx.ALIGN_CENTER, border=5)
        search.AddStretchSpacer(1)
        search.Add(search_label, flag=wx.ALL|wx.ALIGN_CENTER, border=5)
        search.Add(search_edit, flag=wx.ALL|wx.ALIGN_CENTER, border=5)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(search, flag=wx.ALL|wx.EXPAND, border=5)
        sizer.Add(listctrl, 1, flag=wx.ALL|wx.EXPAND, border=5)
        # setup event handlers
        window.Bind(wx.EVT_TEXT, self.OnSearchChange, search_edit)
        # set member variables
        self._search = search_edit
        return sizer

    def CreateListCtrl(self):
        widget = self.ListWidget(self.Window)
        self._listwidget = widget
        self._listctrl = widget.Controls
        return self._listctrl

    def OnSearchChange(self, event):
        """Update element list."""
        selected = self.GetData()               # retrieve selected index
        self.SetData(self.elements, selected)   # filter by search string

    def SetData(self, elements, selected, label=None):
        """Update element list and selection."""
        if label is not None:
            self.label = label
            self.ctrl_label.SetLabel(label)
        self.elements = elements
        searchtext = self._search.GetValue()
        filtered = filter_elements(elements, searchtext)
        self._listwidget.SetData(filtered, selected)

    def GetData(self):
        """Retrieve the index of the selected element."""
        return self._listwidget.GetData()

    def Validate(self, parent):
        return self._listwidget.Validate(parent)


class RangeListWidget(ElementListWidget):

    Style = 0

    def CreateControls(self, window):
        """Create element list and search controls."""
        listctrl = super(RangeListWidget, self).CreateControls(window)
        listctrl.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        return listctrl

    def OnChar(self, event):
        """Apply dialog when pressing Enter."""
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_RETURN:
            self.ApplyDialog()
        # NOTE: we never skip the event, since the default event handler for
        # some keys messes up our selection.
        # TODO: scroll on UP/DOWN?

    def OnLeftDown(self, event):
        """Change selection."""
        selected = self.GetData()
        x, y = event.GetPosition()
        row, col = self._listctrl.GetCellId(x, y)
        if row < 0:
            return
        if self.elements[row][0] >= selected[1]:
            select_end = True
        elif self.elements[row][0] <= selected[0]:
            select_end = False
        else:
            select_end = event.AltDown() or event.ShiftDown()
        element_index = self.elements[row][0]
        if select_end:
            selected[1] = element_index
        else:
            selected[0] = element_index
        self.SetData(self.elements, selected)

    def OnDoubleClick(self, event):
        """Do nothing."""
        event.Skip()

    def Validate(self, parent):
        """Check input validity."""
        return (self._listctrl.GetItemCount() > 1 and
                self._listctrl.GetSelectedItemCount() >= 2)

    def SetData(self, elements, selected):
        """Update element list and selection."""
        self.elements = elements
        self._listctrl.items = elements
        for _i, (i, el) in enumerate(elements):
            if i >= selected[0] and i <= selected[1]:
                self._listctrl.Select(_i, True)
            else:
                self._listctrl.Select(_i, False)

    def GetData(self):
        """Retrieve the index of the selected element."""
        sel = [i for i, el in self._listctrl.selected_items]
        return [min(sel), max(sel)]


class RangeWidget(ElementWidget):

    Title = "Select element range"

    ListWidget = RangeListWidget

    def CreateControls(self, window):
        sizer = super(RangeWidget, self).CreateControls(window)
        help_text = "(Shift click to select last element)"
        help_ctrl = wx.StaticText(window, label=help_text)
        sizer.Add(help_ctrl, flag=wx.ALL|wx.ALIGN_CENTER, border=5)
        return sizer

    def SetData(self, elements, selected):
        """Update element list and selection."""
        self.elements = elements
        searchtext = self._search.GetValue()
        filtered = filter_elements(elements, searchtext, selected)
        self._listwidget.SetData(filtered, selected)
