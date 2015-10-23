"""
Widgets for element selection.
"""

# force new style imports
from __future__ import absolute_import

# GUI components
from madgui.core import wx
from madgui.widget.input import Widget, Dialog, Cancellable
from madgui.widget import listview
from madgui.widget import slider

from madgui.util.unit import strip_unit, units, format_quantity

from wx.combo import ComboCtrl, ComboPopup


# exported symbols
__all__ = [
    'ElementListWidget',
    'SelectElementWidget',
    'ElementPickerWidget',
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
            lambda item: item[0],
            wx.LIST_FORMAT_RIGHT),
        listview.ColumnInfo(
            'Name',
            lambda item: item[1]['name'],
            wx.LIST_FORMAT_LEFT),
        listview.ColumnInfo(
            'Type',
            lambda item: item[1]['type'],
            wx.LIST_FORMAT_LEFT),
        listview.ColumnInfo(
            'At',
            lambda item: format_quantity(item[1]['at'], '.3f'),
            wx.LIST_FORMAT_RIGHT),
    ]

    def CreateControls(self, window):
        """Create element list and search controls."""
        listctrl = listview.ListCtrl(window,
                                     self.column_info,
                                     style=self.Style)
        listctrl.setResizeColumn(1)
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


class SelectElementWidget(Widget):

    """Element selection dialog with a list control and a search box."""

    Title = "Choose element"

    def CreateControls(self, window):
        """Create element list and search controls."""
        # create list control
        listctrl = self.CreateListCtrl()
        # create search control
        self.ctrl_label = label = wx.StaticText(window, label='Select element:')
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
        # TODO: support manage=False by intermediate panel?
        widget = ElementListWidget(self.Window)
        self._listwidget = widget
        self._listctrl = widget.Controls
        return self._listctrl

    def OnSearchChange(self, event):
        """Update element list."""
        selected = self.GetData()               # retrieve selected index
        self.SetData(self.elements, selected)   # filter by search string

    def SetLabel(self, label):
        self.ctrl_label.SetLabel(label)

    def SetData(self, elements, selected):
        """Update element list and selection."""
        self.elements = elements
        searchtext = self._search.GetValue()
        filtered = filter_elements(elements, searchtext)
        self._listwidget.SetData(filtered, selected)

    def GetData(self):
        """Retrieve the index of the selected element."""
        return self._listwidget.GetData()

    def Validate(self, parent):
        return self._listwidget.Validate(parent)


class RangeWidget(slider.DualSlider):

    Title = "Select element range"

    def CreateControls(self, window):
        ctrl = super(RangeWidget, self).CreateControls(window)
        sizer = self.sizer
        self.start_picker = ElementPickerWidget(ctrl, manage=False)
        self.stop_picker = ElementPickerWidget(ctrl, manage=False)
        CENTER_V = wx.ALIGN_CENTER_VERTICAL
        sizer.Insert(0, wx.StaticText(ctrl, label="Begin:"), 0, CENTER_V)
        sizer.Insert(2, self.start_picker.Controls, 1, CENTER_V|wx.EXPAND)
        sizer.Insert(3, wx.StaticText(ctrl, label="End:"), 0, CENTER_V)
        sizer.Insert(5, self.stop_picker.Controls, 1, CENTER_V|wx.EXPAND)
        sizer.AddGrowableCol(1)
        sizer.AddGrowableCol(2)
        self.start_picker.Controls.Bind(wx.EVT_CHOICE, self.OnPickStart)
        self.stop_picker.Controls.Bind(wx.EVT_CHOICE, self.OnPickStop)
        ctrl.Bind(slider.EVT_RANGE_CHANGE_START, self.OnSlideStart)
        ctrl.Bind(slider.EVT_RANGE_CHANGE_STOP, self.OnSlideStop)
        return ctrl

    def SetData(self, elements, selected):
        """Update element list and selection."""
        start, stop = selected
        els = list(enumerate(elements))
        self.start_picker.SetData(els, start)
        self.stop_picker.SetData(els, stop)
        super(RangeWidget, self).SetData(selected, (0, len(elements)-1))

    def OnPickStart(self, event):
        self.ctrl_start.SetValue(event.GetInt())
        self.OnSliderStart(event)

    def OnPickStop(self, event):
        self.ctrl_stop.SetValue(event.GetInt())
        self.OnSliderStop(event)

    def OnSlideStart(self, event):
        self.start_picker.SetSelection(event.start)

    def OnSlideStop(self, event):
        self.stop_picker.SetSelection(event.stop)


class ElementPickerWidget(Widget):

    def CreateControls(self, window):
        self.ctrl = ComboCtrl(window, style=wx.CB_READONLY)
        self.popup = ElementListPopup()
        self.ctrl.SetPopupControl(self.popup)
        return self.ctrl

    def SetElements(self, elements):
        self.popup.SetElements(elements)

    def SetSelection(self, value):
        self.popup.Value = value
        self.UpdateText()

    def SetData(self, elements, selected):
        self.SetElements(elements)
        self.SetSelection(selected)

    def UpdateText(self):
        self.ctrl.SetText(self.popup.GetStringValue())

    def GetData(self):
        """Selected index."""
        return self.popup.Value

    def OnChange(self, event):
        event.Skip()

    def OnGetFocus(self, event):
        self.ctrl.SelectAll()
        event.Skip()


class ElementListPopup(ComboPopup):

    """
    The class that controls the popup part of the ComboCtrl.
    """

    # ComboPopup Overwrites:

    def Create(self, parent):
        """Create the popup child control. Return true for success."""
        self.lcw = ElementListWidget(parent, manage=False)
        self.lc = self.lcw.Controls
        self.lc.Bind(wx.EVT_MOTION, self.OnMotion)
        self.lc.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        self.lc.Bind(wx.EVT_CHAR, self.OnChar)
        return True

    def GetControl(self):
        """Return the widget that is to be used for the popup."""
        return self.lc

    def OnPopup(self):
        self.lc._doResize()
        self.lc.ViewCellRect(self.Value, 0)

    def SetStringValue(self, value):
        """Called just prior to displaying the popup to update the selection."""
        pass

    def GetStringValue(self):
        value = self.Value
        if value < 0:
            return ""
        item = self.lc.items[value]
        return self.lcw.column_info[1].gettext(item)

    def GetAdjustedSize(self, minWidth, prefHeight, maxHeight):
        return (max(minWidth, self.lc.GetTotalWidth()),
                prefHeight if prefHeight > 0 else maxHeight)

    # Own methods

    def SetElements(self, elements):
        self.lc.items = elements

    def OnMotion(self, evt):
        """Select the item currenly under the cursor."""
        item, _ = self.lc.HitTest(evt.GetPosition())
        if item >= 0:
            self.lc.Select(item)

    def OnLeftDown(self, evt):
        """Dismiss the control and use the current value as result."""
        self.Dismiss()

    def OnChar(self, event):
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_RETURN:
            self.Dismiss()

    @property
    def Value(self):
        return self.lc.GetFirstSelected()

    @Value.setter
    def Value(self, value):
        self.lc.Select(value)
