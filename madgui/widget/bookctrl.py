# encoding: utf-8
"""
BookCtrl with Menu made of Panel-items.
"""

# force new style imports
from __future__ import absolute_import

from madgui.core import wx

from wx.lib.agw.flatnotebook import LightColour

# exported symbols
__all__ = [
    'BookCtrl',
    'MenuItem',
    'MenuCtrl',
    'PanelsBook',
]


def RecursiveBind(window, *args, **kwargs):
    window.Bind(*args, **kwargs)
    for child in window.GetChildren():
        RecursiveBind(child, *args, **kwargs)


class _BookEvtEmitter(object):

    def _Fire(self, event_type, sel, old_sel):
        event = wx.BookCtrlEvent(event_type, self.GetId())
        event.SetSelection(sel)
        event.SetOldSelection(old_sel)
        event.SetEventObject(self)
        return not self.ProcessWindowEvent(event) or event.IsAllowed()


class _BookSelect(_BookEvtEmitter):

    def __init__(self):
        self._selection = wx.NOT_FOUND

    def GetSelection(self):
        return self._selection

    def SetSelection(self, new_sel):

        # check parameters
        if isinstance(new_sel, wx.Window):
            new_sel = self._GetIndex(new_sel)
        old_sel = self._selection
        if new_sel == old_sel:
            return

        # listen for vetos
        if not self._Fire(wx.wxEVT_COMMAND_NOTEBOOK_PAGE_CHANGING,
                          new_sel, old_sel):
            return

        self.Freeze()
        try:
            # update selection state
            if old_sel != wx.NOT_FOUND:
                self._Deselect(old_sel)
            self._selection = new_sel
            self._Select(new_sel)
        finally:
            self.Thaw()
        self.GetSizer().Layout()

        # notify the world
        self._Fire(wx.wxEVT_COMMAND_NOTEBOOK_PAGE_CHANGED, new_sel, old_sel)


class BookCtrl(wx.PyPanel, _BookSelect):

    def __init__(self, parent):
        wx.PyPanel.__init__(self, parent)
        _BookSelect.__init__(self)
        self._pages = []
        self._sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self._sizer)

    def AddPage(self, page):
        index = len(self._pages)
        page.Reparent(self)
        self._pages.append(page)
        page.Hide()
        return index

    def DoGetBestSize(self):
        if not self._pages:
            return wx.Size(10, 10)
        w, h = 0, 0
        for page in self._pages:
            wp, hp = page.GetBestSize()
            w, h = max(w, wp), max(h, hp)
        return wx.Size(w, h)

    def _UpdateSize(self):
        pass
        # self._sizer.Layout()
        # self.Refresh()
        # size = self.GetBestSize()
        # for page in self._pages:
        #     page.SetSize(size)
        # root = self.GetTopLevelParent()
        # root.Layout()
        # root.Fit()

    def _Deselect(self, index):
        page = self._pages[index]
        self._sizer.Detach(page)
        page.Hide()

    def _Select(self, index):
        page = self._pages[index]
        page.Show()
        self._sizer.Add(self._pages[index], 1, flag=wx.EXPAND)
        self._UpdateSize()

    def _GetIndex(self, page):
        return self._pages.index(page)


class MenuItem(wx.Panel):

    def OnClick(self, event):
        self.GetParent().SetSelection(self)
        event.Skip()

    def Finish(self):
        RecursiveBind(self, wx.EVT_LEFT_DOWN, self.OnClick)


class MenuCtrl(wx.Panel, _BookSelect):

    def __init__(self, parent, direction=wx.VERTICAL):
        wx.Panel.__init__(self, parent)
        _BookSelect.__init__(self)
        self._items = []
        self._sizer = wx.BoxSizer(direction)
        self.SetSizer(self._sizer)

    def AddItem(self):
        index = len(self._items)
        item = self._CreateItem()
        self._sizer.Add(item, flag=wx.EXPAND)
        self._items.append(item)
        self._Deselect(index)
        return item

    def _CreateItem(self):
        return MenuItem(self, style=wx.RAISED_BORDER)

    def _Select(self, index):
        window = self._items[index]
        window.SetBackgroundColour(LightColour(self.GetBackgroundColour(), 50))
        style = (window.GetWindowStyle() & ~wx.BORDER_MASK) | wx.RAISED_BORDER
        window.SetWindowStyle(style)
        #self._sizer.Layout()
        window.GetParent().Refresh()

    def _Deselect(self, index):
        window = self._items[index]
        window.SetBackgroundColour(self.GetBackgroundColour())
        style = (window.GetWindowStyle() & ~wx.BORDER_MASK) | wx.NO_BORDER
        window.SetWindowStyle(style)
        # self._sizer.Layout()
        window.GetParent().Refresh()

    def _GetIndex(self, item):
        return self._items.index(item)


class PanelsBook(wx.Panel, _BookEvtEmitter):

    Menu = MenuCtrl
    Book = BookCtrl

    def __init__(self, parent):
        super(PanelsBook, self).__init__(parent)
        self.menu = self.Menu(self)
        self.book = self.Book(self)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.menu, flag=wx.EXPAND)
        sizer.AddSpacer(10)
        sizer.Add(self.book, 1, flag=wx.EXPAND)
        self.SetSizer(sizer)

        # catch notebook events from sub-controls:
        NOP = lambda event: None
        self.menu.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGING, self._OnMenuPageChanging)
        self.menu.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._OnMenuPageChanged)
        self.book.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGING, NOP)
        self.book.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, NOP)

    def AddPage(self, page):
        item = self.menu.AddItem()
        self.book.AddPage(page)
        return item

    def SetSelection(self, item):
        self.menu.SetSelection(item)

    def GetSelection(self):
        return self.menu.GetSelection()

    def _OnMenuPageChanging(self, event):
        veto = not self._Fire(event.GetEventType(),
                              event.GetSelection(),
                              event.GetOldSelection())
        if veto:
            event.Veto()

    def _OnMenuPageChanged(self, event):
        self.book.SetSelection(event.GetSelection())
        veto = self._Fire(event.GetEventType(),
                          event.GetSelection(),
                          event.GetOldSelection())
