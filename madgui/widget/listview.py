"""
List view widget.
"""

from madgui.core import wx

from wx.lib.mixins.listctrl import ListCtrlAutoWidthMixin


class ListView(wx.ListView, ListCtrlAutoWidthMixin):

    def __init__(self, *args, **kwargs):
        wx.ListView.__init__(self, *args, **kwargs)
        ListCtrlAutoWidthMixin.__init__(self)
        self.setResizeColumn(0)


#----------------------------------------------------------------------------
#----------------------------------------------------------------------------
from bisect import bisect


class EditListCtrl(wx.ListCtrl):
    """
    A mixin class that enables any text in any column of a
    multi-column listctrl to be edited by clicking on the given row
    and column.  You close the text editor by hitting the ENTER key or
    clicking somewhere else on the listctrl. You switch to the next
    column by hiting TAB.

    To use the mixin you have to include it in the class definition
    and call the __init__ function::

        class TestListCtrl(wx.ListCtrl, TextEditMixin):
            def __init__(self, parent, ID, pos=wx.DefaultPosition,
                         size=wx.DefaultSize, style=0):
                wx.ListCtrl.__init__(self, parent, ID, pos, size, style)
                TextEditMixin.__init__(self)


    Authors:     Steve Zatz, Pim Van Heuven (pim@think-wize.com)
    """

    editorBgColour = wx.Colour(255,255,175) # Yellow
    editorFgColour = wx.Colour(0,0,0)       # black

    def __init__(self, *args, **kwargs):

        super(EditListCtrl, self).__init__(*args, **kwargs)

        self.editor = None
        self.curRow = 0
        self.curCol = 0

        self.Bind(wx.EVT_TEXT_ENTER, self.CloseEditor)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnLeftDown)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected, self)


    def make_editor(self, row, col, col_style=wx.LIST_FORMAT_LEFT):

        editor = self._CreateEditor(row, col, col_style)
        if not editor:
            return

        editor.Control.SetBackgroundColour(self.editorBgColour)
        editor.Control.SetForegroundColour(self.editorFgColour)
        font = self.GetFont()
        editor.Control.SetFont(font)

        self.curRow = row
        self.curCol = col

        editor.Control.Bind(wx.EVT_CHAR, self.OnChar)
        editor.Control.Bind(wx.EVT_KILL_FOCUS, self.CloseEditor)

        return editor


    def OnItemSelected(self, evt):
        self.curRow = evt.GetIndex()
        evt.Skip()


    def OnChar(self, event):
        ''' Catch the TAB, Shift-TAB, cursor DOWN/UP key code
            so we can open the editor at the next column (if any).'''

        keycode = event.GetKeyCode()
        if keycode == wx.WXK_TAB and event.ShiftDown():
            self.CloseEditor()
            if self.curCol-1 >= 0:
                self.OpenEditor(self.curCol-1, self.curRow)

        elif keycode == wx.WXK_TAB:
            self.CloseEditor()
            if self.curCol+1 < self.GetColumnCount():
                self.OpenEditor(self.curCol+1, self.curRow)

        elif keycode == wx.WXK_ESCAPE:
            self.CloseEditor()

        elif keycode == wx.WXK_DOWN:
            self.CloseEditor()
            if self.curRow+1 < self.GetItemCount():
                self._SelectIndex(self.curRow+1)
                self.OpenEditor(self.curCol, self.curRow)

        elif keycode == wx.WXK_UP:
            self.CloseEditor()
            if self.curRow > 0:
                self._SelectIndex(self.curRow-1)
                self.OpenEditor(self.curCol, self.curRow)

        else:
            event.Skip()


    def OnLeftDown(self, evt=None):
        ''' Examine the click and double
        click events to see if a row has been click on twice. If so,
        determine the current row and columnn and open the editor.'''

        if self.editor:
            self.CloseEditor()

        x,y = evt.GetPosition()
        row,flags = self.HitTest((x,y))

        if row != self.curRow: # self.curRow keeps track of the current row
            evt.Skip()
            return

        # the following should really be done in the mixin's init but
        # the wx.ListCtrl demo creates the columns after creating the
        # ListCtrl (generally not a good idea) on the other hand,
        # doing this here handles adjustable column widths

        self.col_locs = [0]
        loc = 0
        for n in range(self.GetColumnCount()):
            loc = loc + self.GetColumnWidth(n)
            self.col_locs.append(loc)

        col = bisect(self.col_locs, x+self.GetScrollPos(wx.HORIZONTAL)) - 1
        self.Touch(row, col)

    def Touch(self, row, col):
        self.OpenEditor(col, row)

    def OpenEditor(self, col, row):
        ''' Opens an editor at the current position. '''

        # give the derived class a chance to Allow/Veto this edit.
        evt = wx.ListEvent(wx.wxEVT_COMMAND_LIST_BEGIN_LABEL_EDIT, self.GetId())
        evt.m_itemIndex = row
        evt.m_col = col
        item = self.GetItem(row, col)
        evt.m_item.SetId(item.GetId())
        evt.m_item.SetColumn(item.GetColumn())
        evt.m_item.SetData(item.GetData())
        evt.m_item.SetText(item.GetText())
        ret = self.GetEventHandler().ProcessEvent(evt)
        if ret and not evt.IsAllowed():
            return   # user code doesn't allow the edit.

        self.CloseEditor()
        editor = self.make_editor(row, col, self.GetColumn(col).m_format)
        if not editor:
            return
        self.editor = editor

        x0 = self.col_locs[col]
        x1 = self.col_locs[col+1] - x0

        scrolloffset = self.GetScrollPos(wx.HORIZONTAL)

        # scroll forward
        if x0+x1-scrolloffset > self.GetSize()[0]:
            if wx.Platform == "__WXMSW__":
                # don't start scrolling unless we really need to
                offset = x0+x1-self.GetSize()[0]-scrolloffset
                # scroll a bit more than what is minimum required
                # so we don't have to scroll everytime the user presses TAB
                # which is very tireing to the eye
                addoffset = self.GetSize()[0]/4
                # but be careful at the end of the list
                if addoffset + scrolloffset < self.GetSize()[0]:
                    offset += addoffset

                self.ScrollList(offset, 0)
                scrolloffset = self.GetScrollPos(wx.HORIZONTAL)
            else:
                # Since we can not programmatically scroll the ListCtrl
                # close the editor so the user can scroll and open the editor
                # again
                return

        y0 = self.GetItemRect(row)[1]

        editor.Control.SetDimensions(x0-scrolloffset,y0, x1,-1)

        editor.Value = self._GetValue(row, col)
        editor.Select()
        editor.Control.Show()
        editor.Control.Raise()
        editor.Control.SetFocus()


    # FIXME: this function is usually called twice - second time because
    # it is binded to wx.EVT_KILL_FOCUS. Can it be avoided? (MW)
    def CloseEditor(self, evt=None):
        ''' Close the editor and save the new value to the ListCtrl. '''
        if not self.editor:
            return
        valid = self.editor.IsValid
        value = self.editor.Value
        text = str(value)
        self.editor.Destroy()
        self.editor = None
        self.SetFocus()

        if not valid:
            return

        # post wxEVT_COMMAND_LIST_END_LABEL_EDIT
        # Event can be vetoed. It doesn't has SetEditCanceled(), what would
        # require passing extra argument to CloseEditor()
        evt = wx.ListEvent(wx.wxEVT_COMMAND_LIST_END_LABEL_EDIT, self.GetId())
        evt.m_itemIndex = self.curRow
        evt.m_col = self.curCol
        item = self.GetItem(self.curRow, self.curCol)
        evt.m_item.SetId(item.GetId())
        evt.m_item.SetColumn(item.GetColumn())
        evt.m_item.SetData(item.GetData())
        evt.m_item.SetText(text) #should be empty string if editor was canceled
        ret = self.GetEventHandler().ProcessEvent(evt)
        if not ret or evt.IsAllowed():
            self._SetValue(self.curRow, self.curCol, value)
        self.RefreshItem(self.curRow)

    def _SelectIndex(self, row):
        listlen = self.GetItemCount()
        if row < 0 and not listlen:
            return
        if row > (listlen-1):
            row = listlen -1

        self.SetItemState(self.curRow, ~wx.LIST_STATE_SELECTED,
                          wx.LIST_STATE_SELECTED)
        self.EnsureVisible(row)
        self.SetItemState(row, wx.LIST_STATE_SELECTED,
                          wx.LIST_STATE_SELECTED)

    def _GetValue(self, row, col):
        return self.GetItem(row, col).GetText()

    def _SetValue(self, row, col, value):
        text = str(value)
        if self.IsVirtual():
            # replace by whather you use to populate the virtual ListCtrl
            # data source
            self.SetVirtualData(self.curRow, self.curCol, text)
        else:
            self.SetStringItem(self.curRow, self.curCol, text)

    def _CreateEditor(self, row, col, col_style):
        raise NotImplementedError
