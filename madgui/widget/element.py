"""
Widgets for element selection.
"""

# force new style imports
from __future__ import absolute_import

# GUI components
from madgui.core import wx
from madgui.widget.input import ModalDialog
from madgui.widget import listview

from madgui.util.unit import strip_unit, units


# exported symbols
__all__ = [
    'ElementControl',
    'ElementDialog',
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


class ElementList(listview.ListView):

    """ListCtrl to display a list of beamline elements."""

    # TODO: support more element properties / move column logic into a
    # separate class, so it can be used elsewhere?

    def __init__(self, parent):
        """Initialize control."""
        # initialize super classes
        style = wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VIRTUAL
        super(ElementList, self).__init__(parent, style=style)
        self.setResizeColumn(2)
        # setup member variables
        self._elements = []
        self._colname = colname = [     # columns in order
            'index',
            'name',
            'type',
            'at',
        ]
        self._colidx = colidx = {       # column index by name
            name: index
            for index, name in enumerate(self._colname)
        }
        # insert columns
        self.InsertColumn(colidx['name'], "Name", width=wx.LIST_AUTOSIZE)
        self.InsertColumn(colidx['type'], "Type", width=wx.LIST_AUTOSIZE)
        self.InsertColumn(colidx['at'], "At [m]", width=wx.LIST_AUTOSIZE,
                          format=wx.LIST_FORMAT_RIGHT)
        self.InsertColumn(colidx['index'], "", width=35,
                          format=wx.LIST_FORMAT_RIGHT)

    @property
    def selected(self):
        """
        Get a tuple (index, element_data) for the currently selected item.

        :raises KeyError: if nothing is selected
        """
        index = self.GetFirstSelected()
        if index == -1:
            raise KeyError
        return self._elements[index]

    @property
    def elements(self):
        """Get displayed elements as an enumeration [(index, element_data)]."""
        return self._elements

    @elements.setter
    def elements(self, new):
        """
        Update widget with new element list.

        :param list new: enumeration of elements [(index, element_data)].
        """
        old = self._elements
        if new == old:
            return
        self._elements = new
        # keep the current selection if possible:
        selected = self.GetFirstSelected()
        if selected >= 0:
            selected_elem = old[selected]
            try:
                selected = new.index(selected_elem)
            except ValueError:
                selected = 0
        else:
            selected = 0
        # update list control
        count = len(new)
        self.SetItemCount(count)
        if count > 0:
            self.RefreshItems(0, count-1)
            self.Select(selected)
            self.Focus(selected)
        self._doResize()

    def OnGetItemText(self, row, col):
        """
        Get the text for the specified row/col.

        Overloading this method is required for *virtual* ListCtrl's.
        """
        index, elem = self._elements[row]
        colname = self._colname[col]
        if colname == 'name':
            return elem['name']
        if colname == 'type':
            return elem['type']
        if colname == 'index':
            return index
        if colname == 'at':
            # show 3 places after the decimal point (=millimeter):
            return '{:.3f}'.format(strip_unit(elem['at'], units.m))


class ElementDialog(ModalDialog):

    """Element selection dialog with a list control and a search box."""

    def SetData(self, elements, selected=0):
        """Initialize data."""
        self.elements = list(elements)
        self.selected = selected

    def CreateContentArea(self):
        """Create element list and search controls."""
        # create list control
        listctrl = ElementList(self)
        listctrl.SetMinSize(wx.Size(400, 200))
        # create search control
        search_label = wx.StaticText(self, label="Search")
        search_edit = wx.TextCtrl(self, style=wx.TE_RICH2)
        search_edit.SetFocus()
        # setup sizers
        search = wx.BoxSizer(wx.HORIZONTAL)
        search.Add(search_label, flag=wx.ALL, border=5)
        search.Add(search_edit, flag=wx.ALL, border=5)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(search, flag=wx.ALL|wx.ALIGN_RIGHT, border=5)
        sizer.Add(listctrl, 1, flag=wx.ALL|wx.EXPAND, border=5)
        # setup event handlers
        self.Bind(wx.EVT_TEXT, self.OnSearchChange, search_edit)
        listctrl.Bind(wx.EVT_CHAR, self.OnChar)
        listctrl.Bind(wx.EVT_LEFT_DCLICK, self.OnDoubleClick)
        # set member variables
        self._listctrl = listctrl
        self._search = search_edit
        return sizer

    def OnSearchChange(self, event):
        """Update element list."""
        self.TransferDataToWindow()

    def OnChar(self, event):
        """Apply dialog when pressing Enter."""
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_RETURN and self.CanApply():
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

    def TransferDataToWindow(self):
        """Update element list and selection."""
        searchtext = self._search.GetValue()
        filtered_elements = filter_elements(self.elements, searchtext)
        self._listctrl.elements = filtered_elements
        try:
            sel_index = self.selected
            sel_element = self.elements[sel_index]
            selected = filtered_elements.index((sel_index, sel_element))
        except (IndexError, ValueError):
            return
        self._listctrl.Select(selected)
        self._listctrl.Focus(selected)

    def TransferDataFromWindow(self):
        """Retrieve the index of the selected element."""
        self.selected = self._listctrl.selected

    def CreateOkButton(self):
        """Create 'Ok' button."""
        button = super(ElementDialog, self).CreateOkButton()
        self.Bind(wx.EVT_UPDATE_UI, self.UpdateButtonOk, source=button)
        return button

    def UpdateButtonOk(self, event):
        """Disable OK button if no element is selected."""
        event.Enable(self.CanApply())

    def CanApply(self):
        """Check if an item is selected."""
        return (self._listctrl.GetItemCount() > 0 and
                self._listctrl.GetSelectedItemCount() == 1)
