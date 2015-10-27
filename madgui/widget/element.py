"""
Widgets for element selection.
"""

# TODO: increase textctrl width for element picker
# TODO: use of monospace

# force new style imports
from __future__ import absolute_import

# GUI components
from madgui.core import wx
from madgui.widget.input import Widget
from madgui.widget import listview
from madgui.widget import slider

from madgui.util.unit import format_quantity

from wx.combo import ComboCtrl, ComboPopup


# exported symbols
__all__ = [
    'ElementListWidget',
    'ElementPickerWidget',
    'RangeWidget',
]


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
        """Create element list."""
        listctrl = listview.ListCtrl(window,
                                     self.column_info,
                                     style=self.Style)
        listctrl.setResizeColumn(1)
        listctrl.SetMinSize(wx.Size(400, 200))
        self._listctrl = listctrl
        return listctrl

    def Validate(self):
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
        self.lsw = ElementListWidget(parent, manage=False)
        self.lc = self.lsw.Control
        self.lc.Bind(wx.EVT_MOTION, self.OnMotion)
        self.lc.Bind(wx.EVT_LEFT_DOWN, self.ActivateItem)
        self.lc.Bind(wx.EVT_CHAR, self.OnChar)
        self.lc.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.ActivateItem)
        return True

    def GetControl(self):
        """Return the widget that is to be used for the popup."""
        return self.lc

    def OnPopup(self):
        self.lc._doResize()
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
        comboctrl = self.GetCombo()
        ev = wx.PyCommandEvent(wx.EVT_CHOICE.typeId, comboctrl.GetId())
        ev.SetInt(self.value)
        wx.PostEvent(comboctrl.GetEventHandler(), ev)

    def GetStringValue(self):
        try:
            index = GetItemIndexById(self.elements, self.value)
        except ValueError:
            return ""
        item = self.elements[index]
        return self.lsw.column_info[1].gettext(item)

    def GetAdjustedSize(self, minWidth, prefHeight, maxHeight):
        lc_width = self.lc.GetTotalWidth()
        return (max(minWidth, lc_width),
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
