# encoding: utf-8
"""
Menu creation utilities.
"""

# force new style imports
from __future__ import absolute_import

# GUI components
from madgui.core import wx


__all__ = [
    'Item',
    'Menu',
    'Separator',
    'extend',
]


class Item(object):

    def __init__(self, title, description, action, update_ui=None,
                 kind=wx.ITEM_NORMAL, id=wx.ID_ANY):
        self.title = title
        self.action = action
        self.description = description
        self.update_ui = update_ui
        self.kind = kind
        self.id = id

    def append_to(self, menu, evt_handler):
        item = menu.Append(self.id, self.title, self.description, self.kind)
        evt_handler.Bind(wx.EVT_MENU, self.action, item)
        if self.update_ui:
            evt_handler.Bind(wx.EVT_UPDATE_UI, self.update_ui, item)


class CondItem(Item):

    def __init__(self, title, description, action, condition=None,
                 kind=wx.ITEM_NORMAL, id=wx.ID_ANY):
        self.title = title
        self._action = action
        self.description = description
        self._condition = condition
        self.kind = kind
        self.id = id

    def condition(self):
        if self._condition:
            return self._condition()
        return True

    def action(self, event):
        if self.condition():
            self._action()

    def update_ui(self, event):
        event.Enable(self.condition())


class Menu(object):

    def __init__(self, title, items):
        self.title = title
        self.items = items

    def append_to(self, menu, evt_handler):
        submenu = wx.Menu()
        menu.Append(submenu, self.title)
        extend(evt_handler, submenu, self.items)


class Separator(object):

    @classmethod
    def append_to(cls, menu, evt_handler):
        menu.AppendSeparator()


def extend(evt_handler, menu, items):
    """
    Append menu items to menu.
    """
    for item in items:
        item.append_to(menu, evt_handler)
