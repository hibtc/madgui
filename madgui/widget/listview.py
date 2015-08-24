# encoding: utf-8
"""
List view widgets.
"""

from __future__ import absolute_import

from bisect import bisect
from collections import MutableSequence

from madgui.core import wx
from madgui.util.common import instancevars

# exported symbols
__all__ = [
    'ColumnInfo',
    'ListCtrlUtil',
    'ListCtrlAutoWidthMixin',
    'ListCtrl',
    'EditListCtrl',

    'BaseValue',
    'ReadOnly',
    'StringValue',
    'QuotedStringValue',
    'FloatValue',
    'BoolValue',
    'BaseEditor',
    'StringEditor',
    'ReadOnlyEditor',
    'FloatEditor',
]


class ColumnInfo(object):

    @instancevars
    def __init__(self, title, gettext, format=wx.LIST_FORMAT_LEFT,
                 width=wx.LIST_AUTOSIZE):
        """
        :param str title: column title
        :param callable gettext: (index, item) -> str
        :param int format: format argument for InsertColumn
        :param int width: width argument for InsertColumn
        """
        pass


class ListCtrlUtil(object):

    """Utility to transform window coordinates to row/col and vice versa."""

    def GetCellId(self, x, y):
        """Transform window (x, y) position to logical (row, col) coords."""
        row, flags = self.HitTest((x, y))
        col = bisect(self.col_locs, x + self.GetScrollPos(wx.HORIZONTAL)) - 1
        return row, col

    def ViewCellRect(self, row, col):

        """
        Scroll the specified cell into position if possible and return the
        (x0, y0, width, height) of the specified cell.
        """

        col_locs = self.col_locs
        x0 = col_locs[col]
        x1 = col_locs[col + 1]

        scrolloffset = self.GetScrollPos(wx.HORIZONTAL)

        # scroll forward
        if x1 - scrolloffset > self.GetSize()[0]:
            if wx.Platform == "__WXMSW__":
                # don't start scrolling unless we really need to
                offset = x1 - self.GetSize()[0] - scrolloffset
                # scroll a bit more than what is minimum required
                # so we don't have to scroll everytime the user presses TAB
                # which is very tireing to the eye
                addoffset = self.GetSize()[0] / 4
                # but be careful at the end of the list
                if addoffset + scrolloffset < self.GetSize()[0]:
                    offset += addoffset

                self.ScrollList(offset, 0)
                scrolloffset = self.GetScrollPos(wx.HORIZONTAL)
            else:
                # Since we can not programmatically scroll the ListCtrl
                # close the editor so the user can scroll and open the editor
                # again
                return None

        y0, _, height = self.GetItemRect(row)[1:]

        return (x0 - scrolloffset, y0, x1 - x0, height)

    @property
    def col_locs(self):
        """Starting positions (x coordinates) of each column."""
        # The column positions must be recomputed each time so adjustable
        # column widths are handled properly:
        col_locs = [0]
        loc = 0
        for n in range(self.GetColumnCount()):
            loc = loc + self.GetColumnWidth(n)
            col_locs.append(loc)
        return col_locs


# This class is originally copied from the module `wx.lib.mixins.listctrl`
# distributed with wxPython. See the original source file for authorship.

class ListCtrlAutoWidthMixin:
    """ A mix-in class that automatically resizes the last column to take up
        the remaining width of the wx.ListCtrl.

        This causes the wx.ListCtrl to automatically take up the full width of
        the list, without either a horizontal scroll bar (unless absolutely
        necessary) or empty space to the right of the last column.

        NOTE:    This only works for report-style lists.

        WARNING: If you override the EVT_SIZE event in your wx.ListCtrl, make
                 sure you call event.Skip() to ensure that the mixin's
                 _OnResize method is called.

        This mix-in class was written by Erik Westra <ewestra@wave.co.nz>
    """
    def __init__(self):
        """ Standard initialiser.
        """
        self._resizeColMinWidth = None
        self._resizeColStyle = "LAST"
        self._resizeCol = 0
        self.Bind(wx.EVT_SIZE, self._onResize)
        self.Bind(wx.EVT_LIST_COL_END_DRAG, self._onResize, self)


    def setResizeColumn(self, col):
        """
        Specify which column that should be autosized.  Pass either
        'LAST' or the column number.  Default is 'LAST'.
        """
        if col == "LAST":
            self._resizeColStyle = "LAST"
        else:
            self._resizeColStyle = "COL"
            self._resizeCol = col


    def resizeLastColumn(self, minWidth):
        """ Resize the last column appropriately.

            If the list's columns are too wide to fit within the window, we use
            a horizontal scrollbar.  Otherwise, we expand the right-most column
            to take up the remaining free space in the list.

            This method is called automatically when the wx.ListCtrl is resized;
            you can also call it yourself whenever you want the last column to
            be resized appropriately (eg, when adding, removing or resizing
            columns).

            'minWidth' is the preferred minimum width for the last column.
        """
        self.resizeColumn(minWidth)


    def resizeColumn(self, minWidth):
        self._resizeColMinWidth = minWidth
        self._doResize()


    # =====================
    # == Private Methods ==
    # =====================

    def _onResize(self, event):
        """ Respond to the wx.ListCtrl being resized.

            We automatically resize the last column in the list.
        """
        if 'gtk2' in wx.PlatformInfo or 'gtk3' in wx.PlatformInfo:
            self._doResize()
        else:
            wx.CallAfter(self._doResize)
        event.Skip()


    def _doResize(self):
        """ Resize the last column as appropriate.

            If the list's columns are too wide to fit within the window, we use
            a horizontal scrollbar.  Otherwise, we expand the right-most column
            to take up the remaining free space in the list.

            We remember the current size of the last column, before resizing,
            as the preferred minimum width if we haven't previously been given
            or calculated a minimum width.  This ensure that repeated calls to
            _doResize() don't cause the last column to size itself too large.
        """

        if not self:  # avoid a PyDeadObject error
            return

        if self.GetSize().height < 32:
            return  # avoid an endless update bug when the height is small.

        numCols = self.GetColumnCount()
        if numCols == 0: return # Nothing to resize.

        if(self._resizeColStyle == "LAST"):
            resizeCol = self.GetColumnCount()
        else:
            resizeCol = self._resizeCol

        resizeCol = max(1, resizeCol)

        if self._resizeColMinWidth == None:
            self._resizeColMinWidth = self.GetColumnWidth(resizeCol - 1)

        # We're showing the vertical scrollbar -> allow for scrollbar width
        # NOTE: on GTK, the scrollbar is included in the client size, but on
        # Windows it is not included
        listWidth = self.GetClientSize().width
        if wx.Platform != '__WXMSW__':
            if self.GetItemCount() > self.GetCountPerPage():
                scrollWidth = wx.SystemSettings_GetMetric(wx.SYS_VSCROLL_X)
                listWidth = listWidth - scrollWidth

        totColWidth = 0 # Width of all columns except last one.
        for col in range(numCols):
            if col != (resizeCol-1):
                totColWidth = totColWidth + self.GetColumnWidth(col)

        resizeColWidth = self.GetColumnWidth(resizeCol - 1)

        if totColWidth + self._resizeColMinWidth > listWidth:
            # We haven't got the width to show the last column at its minimum
            # width -> set it to its minimum width and allow the horizontal
            # scrollbar to show.
            self.SetColumnWidth(resizeCol-1, self._resizeColMinWidth)
            return

        # Resize the last column to take up the remaining available space.

        self.SetColumnWidth(resizeCol-1, listWidth - totColWidth)


class ListCtrlList(MutableSequence):

    """A list-like interface adapter for a LC_VIRTUAL wx.ListCtrl."""

    def __init__(self, ctrl, items):
        """Use the items object by reference."""
        self._items = items
        self._ctrl = ctrl

    # Sized

    def __len__(self):
        return len(self._items)

    # Iterable

    def __iter__(self):
        return iter(self._items)

    # Container

    def __contains__(self, value):
        return value in self._items

    # Sequence

    def __getitem__(self, index):
        return self._items[index]

    def __reversed__(self):
        return reversed(self._items)

    def index(self, value):
        return self._items.index(value)

    def count(self, value):
        return self._items.count(value)

    # MutableSequence

    def __setitem__(self, index, value):
        self._items[index] = value
        if isinstance(index, slice):
            self._refresh(0 if index.start is None else index.start,
                          -1 if index.stop is None else index.stop)
        else:
            self._refresh(index, index + 1)

    def __delitem__(self, index):
        del self._items[index]
        self._refresh(index, -1)

    def insert(self, index, value):
        self._items.insert(index, value)
        self._refresh(index, -1)

    append = MutableSequence.append

    def reverse(self):
        self._items.reverse()
        self._refresh(0, -1)

    def extend(self, values):
        old_len = len(self._items)
        self._items.extend(values)
        self._refresh(old_len, -1)

    pop = MutableSequence.pop
    remove = MutableSequence.remove
    __iadd__ = MutableSequence.__iadd__

    def _refresh(self, begin, end):
        count = len(self._items)
        self._ctrl.SetItemCount(count)
        if begin < 0:
            begin = max(0, begin+count)
        if end < 0:
            end += count + 1
        if end > begin:
            self._ctrl.RefreshItems(min(begin, count-1),
                                    min(end-1, count-1))


# need to use ListCtrl, since ListView doesn't work in *virtual* mode:
class ListCtrl(wx.ListCtrl, ListCtrlAutoWidthMixin, ListCtrlUtil):

    """
    Virtual ListCtrl that uses a list of :class:`ColumnInfo` to format its
    columns. The first column is auto-sized by default.
    """

    # TODO: support Ctrl-A + mouse selection
    # TODO: setter for selected_items/selected_indices

    def __init__(self, parent, columns, style=wx.LC_SINGLE_SEL):
        """
        Initialize list view.

        :param list columns: list of :class:`ColumnInfo`
        """
        # initialize super classes
        style |= wx.LC_REPORT | wx.LC_VIRTUAL
        wx.ListCtrl.__init__(self, parent, style=style)
        ListCtrlAutoWidthMixin.__init__(self)
        self.setResizeColumn(0)
        # setup member variables
        self._items = ListCtrlList(self, [])
        self._columns = columns
        # insert columns
        for idx, col in enumerate(self._columns):
            self.InsertColumn(idx, col.title, col.format, col.width)

    @property
    def selected_items(self):
        """Iterate over all selected items."""
        return [self.items[idx] for idx in self.selected_indices]

    @property
    def selected_indices(self):
        """Iterate over all selected indices."""
        idx = self.GetFirstSelected()
        while idx != -1:
            yield idx
            idx = self.GetNextSelected(idx)

    @property
    def items(self):
        """Get list of data items."""
        return self._items

    @items.setter
    def items(self, items):
        """
        Update widget with new item list.

        :param list items: list of data items.
        """
        self._items[:] = items
        # TODO: keep the current selection if possible
        self._doResize()

    def OnGetItemText(self, row, col):
        """Get the text for the specified row/col."""
        return self._columns[col].gettext(row, self._items[row])


### Value handlers

class BaseValue(object):

    """Wrap a value of a specific type for string rendering and editting."""

    default = ""

    def __init__(self, value, default=None):
        """Store the value."""
        self.value = value
        if default is not None:
            self.default = default

    def __str__(self):
        """Render the value."""
        return self.format(self.value)

    @classmethod
    def format(cls, value):
        """Render a value of this type as a string."""
        if value is None:
            return ""
        return str(value)

    @classmethod
    def initiate_edit(cls, parent, row, col):
        """Allow the user to change this value."""
        parent.OpenEditor(row, col)

    @classmethod
    def create_editor(cls, parent):
        """Create an edit control to edit a value of this type."""
        raise NotImplementedError


class ReadOnly(BaseValue):

    """Read-only value."""

    @classmethod
    def create_editor(cls, parent):
        """Create a read-only text editor."""
        return ReadOnlyEditor(parent)


class StringValue(BaseValue):

    """Arbitrary string value."""

    @classmethod
    def create_editor(cls, parent):
        """Create a text editor."""
        return StringEditor(parent)


class QuotedStringValue(StringValue):

    """String value, but format with enclosing quotes."""

    @classmethod
    def format(cls, value):
        """Quote string."""
        if value is None:
            return ""
        fmt = repr(value)
        if fmt.startswith('u'):
            return fmt[1:]
        return fmt


class FloatValue(BaseValue):

    """Float value."""

    default = 0.0

    @classmethod
    def create_editor(cls, parent):
        """Create editor for floats."""
        return FloatEditor(parent)


class BoolValue(BaseValue):

    """Boolean value."""

    default = False

    @classmethod
    def initiate_edit(cls, parent, row, col):
        """Negate value."""
        parent.SetItemValue(row, col, not parent.GetItemValue(row, col))

    @classmethod
    def create_editor(self, parent):
        """
        There is no need for a separate editor - the value can be inverted by
        clicking on it.
        """
        return None


### Editors

class BaseEditor(object):

    """
    Base for accessor classes for typed GUI-controls.
    """

    @property
    def Value(self):
        """Get the current value."""
        raise NotImplementedError

    @Value.setter
    def Value(self, value):
        """Set the current value."""
        raise NotImplementedError

    def Destroy(self):
        """Destroy the control."""
        self.Control.Destroy()
        self.Control = None

    def SelectAll(self):
        """Select all text in the control."""
        raise NotImplementedError


class StringEditor(BaseEditor):

    """Manages an edit control for single-line text."""

    style = wx.TE_PROCESS_ENTER | wx.TE_PROCESS_TAB | wx.TE_RICH2 | wx.TE_LEFT

    bg_color = wx.Colour(255, 255, 175) # yellow
    fg_color = wx.Colour(0, 0, 0)       # black

    def __init__(self, parent):
        """Create a new wx.TextCtrl."""
        self.Control = wx.TextCtrl(parent, style=self.style)
        self.Control.SetBackgroundColour(self.bg_color)
        self.Control.SetForegroundColour(self.fg_color)

    @property
    def Value(self):
        """Get the value of the control."""
        return self.Control.GetValue()

    @Value.setter
    def Value(self, value):
        """Set the value of the control."""
        self.Control.SetValue(str(value))

    def SelectAll(self):
        """Select all text."""
        self.Control.SetSelection(-1,-1)


class ReadOnlyEditor(StringEditor):

    """Manages a read-only edit control for single-line text."""

    style = StringEditor.style | wx.TE_READONLY
    value = None

    bg_color = wx.Colour(200, 200, 200) # gray

    @property
    def Value(self):
        """Get current value."""
        return self.value

    @Value.setter
    def Value(self, value):
        """Set current value."""
        self.value = value
        self.Control.SetValue(str(value))


class FloatEditor(StringEditor):

    """Manages an edit control for floats."""

    style = wx.TE_PROCESS_ENTER | wx.TE_PROCESS_TAB | wx.TE_RICH2 | wx.TE_RIGHT

    @property
    def Value(self):
        """Get the value of the control."""
        value = self.Control.GetValue()
        if not value:
            return None
        return float(value)

    @Value.setter
    def Value(self, value):
        """Set the value of the control."""
        self.Control.SetValue(str(value))


class EditListCtrl(wx.ListCtrl, ListCtrlUtil):

    """
    A multi-column list control that allows the values in any entry to be
    edited by clicking on it. You close the text editor by hitting the ENTER
    key or clicking somewhere else on the listctrl. You switch to the next
    edittable cell by hiting TAB.

    Authors:    Steve Zatz,
                Pim Van Heuven (pim@think-wize.com),
                Thomas Gläßle
    """

    def __init__(self, *args, **kwargs):

        """Create window and setup event handling."""

        super(EditListCtrl, self).__init__(*args, **kwargs)

        self.editor = None
        self.curRow = 0
        self.curCol = 0
        self.items = []
        self.column_types = {}

        self.Bind(wx.EVT_TEXT_ENTER, self.CloseEditor)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnLeftDown)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected, self)

    def OnItemSelected(self, event):
        """Keep track of current row."""
        self.curRow = event.GetIndex()
        event.Skip()

    def OnChar(self, event):

        """
        Open/close the editor appropriately on key events.

        - Tab/Shift+Tab     move editor to next/previous edittable item
        - Return/Escape     stop editting
        - Up/Down           move editor one up/down
        """

        keycode = event.GetKeyCode()

        if keycode == wx.WXK_TAB and event.ShiftDown():
            self.CloseEditor()
            col_count = self.GetColumnCount()
            cur_index = self.curRow * col_count + self.curCol
            for index in reversed(range(cur_index)):
                row, col = divmod(index, col_count)
                if not issubclass(self.GetItemType(row, col), ReadOnly):
                    self._SelectIndex(row)
                    self.OpenEditor(row, col)
                    break

        elif keycode == wx.WXK_TAB:
            self.CloseEditor()
            col_count = self.GetColumnCount()
            cur_index = self.curRow * col_count + self.curCol
            max_index = self.GetItemCount() * col_count
            for index in range(cur_index + 1, max_index):
                row, col = divmod(index, col_count)
                if not issubclass(self.GetItemType(row, col), ReadOnly):
                    self._SelectIndex(row)
                    self.OpenEditor(row, col)
                    break

        elif keycode == wx.WXK_RETURN:
            self.CloseEditor()

        elif keycode == wx.WXK_ESCAPE:
            self.CloseEditor()

        elif keycode == wx.WXK_DOWN:
            self.CloseEditor()
            if self.curRow+1 < self.GetItemCount():
                self._SelectIndex(self.curRow+1)
                self.OpenEditor(self.curRow, self.curCol)

        elif keycode == wx.WXK_UP:
            self.CloseEditor()
            if self.curRow > 0:
                self._SelectIndex(self.curRow-1)
                self.OpenEditor(self.curRow, self.curCol)

        else:
            event.Skip()

    def OnLeftDown(self, event=None):
        """
        Close the editor when clicking somewhere else. Open an editor or
        switch the value if clicking twice on some item.
        """
        if self.editor:
            self.CloseEditor()
        x, y = event.GetPosition()
        row, col = self.GetCellId(x, y)
        if row != self.curRow:
            event.Skip()
            return
        # Don't ask me why, but for some reason (at least on my wxGTK) the
        # editor receives a KILL_FOCUS event right after being opened by a
        # single left click. Delaying editor creation circumvents the issue:
        wx.CallAfter(self.GetItemType(row, col).initiate_edit, self, row, col)

    def OpenEditor(self, row, col):

        """Opens an editor for the specified item."""

        self.CloseEditor()

        self.curRow = row
        self.curCol = col

        rect = self.ViewCellRect(row, col)
        if rect is None:
            return
        x, y, w, h = rect

        # If using 'self' as parent for the editor, the SetFocus() call down
        # the road will cause weird displacements if the list control is
        # scrolled vertically (wxGTK).
        x += self.GetRect()[0]
        y += self.GetRect()[1]
        editor = self.GetItemType(row, col).create_editor(self.GetParent())
        if not editor:
            return
        self.editor = editor

        editor.Control.SetDimensions(x, y, w, h)
        editor.Control.SetFont(self.GetFont())

        editor.Control.Show()
        editor.Control.Raise()
        editor.Control.SetFocus()

        editor.Value = self.GetItemValueOrDefault(row, col)
        editor.SelectAll()

        editor.Control.Bind(wx.EVT_CHAR, self.OnChar)
        editor.Control.Bind(wx.EVT_KILL_FOCUS, self.CloseEditor)

    # FIXME: this function is usually called twice - second time because
    # it is binded to wx.EVT_KILL_FOCUS. Can it be avoided? (MW)
    def CloseEditor(self, event=None):
        """Close the editor and save the new value to the ListCtrl."""
        if not self.editor:
            return
        try:
            value = self.editor.Value
        except ValueError:
            return
        finally:
            self.editor.Destroy()
            self.editor = None
            self.SetFocus()
        text = self.GetItemType(self.curRow, self.curCol).format(value)
        self.SetItemValue(self.curRow, self.curCol, value)

    def _SelectIndex(self, row):
        """Select+focus the specified row."""
        self.SetItemState(self.curRow, ~wx.LIST_STATE_SELECTED,
                          wx.LIST_STATE_SELECTED)
        self.EnsureVisible(row)
        self.SetItemState(row, wx.LIST_STATE_SELECTED,
                          wx.LIST_STATE_SELECTED)
        self.Focus(row)
        self.Select(row)

    # public API

    def InsertRow(self, row, columns=()):
        """Insert a row."""
        self.items.insert(row, {})
        self.InsertStringItem(row, "")
        for col, value in enumerate(columns):
            self.SetItemValue(row, col, value)

    def SetColumnType(self, col, val_type):
        """Set default value type of a column."""
        self.column_types[col] = val_type

    def GetItemType(self, row, col):
        """Get value type of the specified row/column."""
        try:
            return type(self.items[row][col])
        except KeyError:
            return self.column_types.get(col, ReadOnly)

    def GetItemValue(self, row, col):
        """Get the value associated with the specified row/column."""
        try:
            return self.items[row][col].value
        except KeyError:
            return None

    def GetItemValueOrDefault(self, row, col):
        """Get the value or the default."""
        try:
            item = self.items[row][col]
            if item.value is None:
                return item.default
            else:
                return item.value
        except KeyError:
            return self.GetColumnType(col).default

    def SetItemValue(self, row, col, value):
        """Set the value associated with the specified row/column."""
        if not isinstance(value, BaseValue):
            value = self.GetItemType(row, col)(value)
        self.items[row][col] = value
        self.SetStringItem(row, col, str(value))
