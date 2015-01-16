# encoding: utf-8
"""
List view widgets.
"""

from bisect import bisect

from madgui.core import wx

from wx.lib.mixins.listctrl import ListCtrlAutoWidthMixin


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


class ListView(wx.ListView, ListCtrlAutoWidthMixin, ListCtrlUtil):

    """ListView that auto-sizes the first column."""

    def __init__(self, *args, **kwargs):
        """Initialize window."""
        wx.ListView.__init__(self, *args, **kwargs)
        ListCtrlAutoWidthMixin.__init__(self)
        self.setResizeColumn(0)


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
