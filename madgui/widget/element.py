"""
Widgets for element selection.
"""

# TODO: increase textctrl width for element picker
# TODO: use of monospace

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


def GetItemIndexById(items, el_id):
    for _i, (i, el) in enumerate(items):
        if i == el_id:
            return _i
    raise ValueError("Element index out of range.")


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
            'i',
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

    def CreateControl(self, window):
        """Create element list and search controls."""
        listctrl = listview.ListCtrl(window,
                                     self.column_info,
                                     style=self.Style)
        listctrl.setResizeColumn(1)
        listctrl.SetMinSize(wx.Size(400, 200))
        self._listctrl = listctrl
        return listctrl

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
        listctrl = self.CreateListCtrl(window)
        # create search control
        self.ctrl_label = label = wx.StaticText(window, label='Select element:')
        search_label = wx.StaticText(window, label="Search:")
        search_edit = wx.TextCtrl(window, style=wx.TE_RICH2|wx.TE_PROCESS_ENTER)
        search_edit.SetFocus()
        # setup sizers
        search = wx.BoxSizer(wx.HORIZONTAL)
        search.Add(label, flag=wx.ALL|wx.ALIGN_CENTER, border=5)
        search.AddStretchSpacer(1)
        search.Add(search_label, flag=wx.ALL|wx.ALIGN_CENTER, border=5)
        search.Add(search_edit, 2, flag=wx.ALL|wx.ALIGN_CENTER, border=5)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(search, flag=wx.ALL|wx.EXPAND, border=5)
        sizer.Add(listctrl, 1, flag=wx.ALL|wx.EXPAND, border=5)
        # setup event handlers
        search_edit.Bind(wx.EVT_TEXT, self.OnSearchChange)
        # set member variables
        self._search = search_edit
        return sizer

    def CreateListCtrl(self, parent):
        widget = ElementListWidget(parent, manage=False)
        self._listwidget = widget
        self._listctrl = widget.Control
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
        sizer = super(RangeWidget, self).CreateControls(window)
        self.start_picker = ElementPickerWidget(window, manage=False)
        self.stop_picker = ElementPickerWidget(window, manage=False)
        CENTER_V = wx.ALIGN_CENTER_VERTICAL
        sizer.Insert(0, wx.StaticText(window, label="Begin:"), 0, CENTER_V)
        sizer.Insert(2, self.start_picker.Control, 1, CENTER_V|wx.EXPAND)
        sizer.Insert(3, wx.StaticText(window, label="End:"), 0, CENTER_V)
        sizer.Insert(5, self.stop_picker.Control, 1, CENTER_V|wx.EXPAND)
        sizer.AddGrowableCol(1)
        sizer.AddGrowableCol(2)
        self.start_picker.Control.Bind(wx.EVT_CHOICE, self.OnPickStart)
        self.stop_picker.Control.Bind(wx.EVT_CHOICE, self.OnPickStop)
        window.Bind(slider.EVT_RANGE_CHANGE_START, self.OnSlideStart)
        window.Bind(slider.EVT_RANGE_CHANGE_STOP, self.OnSlideStop)
        return sizer

    def SetData(self, elements, selected):
        """Update element list and selection."""
        start, stop = selected
        els = list(enumerate(elements))
        self.start_picker.SetData(els, start)
        self.stop_picker.SetData(els, stop)
        super(RangeWidget, self).SetData(selected, (0, len(els)-1))

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

    def CreateControl(self, window):
        ctrl = ComboCtrl(window, style=wx.CB_READONLY)
        self.popup = ElementListPopup()
        ctrl.SetPopupControl(self.popup)
        ctrl.Bind(wx.EVT_COMBOBOX_CLOSEUP, self.OnChange)
        return ctrl

    def SetSelection(self, value):
        self.popup.value = value
        self.UpdateText()

    def SetData(self, elements, selected):
        self.popup.SetData(elements, selected)
        self.UpdateText()

    def UpdateText(self):
        self.Control.SetText(self.popup.GetStringValue())

    def GetData(self):
        """Selected index."""
        return self.popup.value

    def OnChange(self, event):
        ev = wx.PyCommandEvent(wx.EVT_CHOICE.typeId, self.Control.GetId())
        ev.SetInt(self.GetData())
        wx.PostEvent(self.Control.GetEventHandler(), ev)

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
        self.lsw = SelectElementWidget(parent, manage=False)
        self.lcw = self.lsw._listwidget
        self.lc = self.lsw._listctrl
        self.lc.Bind(wx.EVT_MOTION, self.OnMotion)
        self.lc.Bind(wx.EVT_LEFT_DOWN, self.ActivateItem)
        self.lc.Bind(wx.EVT_CHAR, self.OnChar)
        self.lc.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.ActivateItem)
        self.lsw._search.Bind(wx.EVT_TEXT_ENTER, self.ActivateItem)
        return True

    def GetControl(self):
        """Return the widget that is to be used for the popup."""
        return self.lsw.Control

    def OnPopup(self):
        self.lc._doResize()
        self.lsw._search.Clear()
        self.lsw._search.SetFocus()
        self._UpdateSelection()

    def _UpdateSelection(self):
        try:
            sel = [GetItemIndexById(self.lc.items, self.value)]
        except ValueError:
            sel = []
        self.lc.selected_indices = sel

    def OnDismiss(self):
        try:
            self.value = self.lsw.GetData()[0]
        except IndexError:
            return

    def GetStringValue(self):
        try:
            index = GetItemIndexById(self.elements, self.value)
        except ValueError:
            return ""
        item = self.elements[index]
        return self.lcw.column_info[1].gettext(item)

    def GetAdjustedSize(self, minWidth, prefHeight, maxHeight):
        lc_width = self.lc.GetTotalWidth()
        self.lsw.Control.Layout()
        diff_w = self.lsw.Control.GetSize()[0] - self.lc.GetSize()[0]
        tot_width = diff_w + lc_width
        return (max(minWidth, tot_width),
                prefHeight if prefHeight > 0 else maxHeight)

    # Own methods

    def SetData(self, elements, selected):
        self.elements = elements
        self.value = selected
        self.lsw.SetData(elements, [selected])

    def OnMotion(self, evt):
        """Select the item currenly under the cursor."""
        item, _ = self.lc.HitTest(evt.GetPosition())
        if item >= 0:
            self.lc.Select(item)

    def ActivateItem(self, evt=None):
        """Dismiss the control and use the current value as result."""
        self.Dismiss()

    def OnChar(self, event):
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_RETURN:
            self.ActivateItem()
        else:
            event.Skip()

    value = -1
