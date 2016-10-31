# encoding: utf-8
"""
Menu creation utilities.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from six import string_types

from madqt.qt import QtCore, QtGui


__all__ = [
    'Item',
    'CondItem',
    'Menu',
    'Separator',
    'extend',
]


class Item(object):

    def __init__(self, label, shortcut, description, action, icon=None,
                 checkable=False):
        self.label = label
        self.shortcut = shortcut
        self.description = description
        self.action = action
        self.icon = icon
        self.checkable = checkable

    def append_to(self, menu, parent=None):
        if parent is None:
            parent = menu
        action = QtGui.QAction(self.label, parent, checkable=self.checkable)
        if self.shortcut is not None:
            action.setShortcut(self.shortcut)
        if self.description is not None:
            action.setStatusTip(self.description)
        if self.action is not None:
            action.triggered.connect(self.action)
        if self.icon is not None:
            if isinstance(self.icon, QtGui.QStyle.StandardPixmap):
                icon = parent.style().standardIcon(self.icon)
            elif isinstance(self.icon, string_types):
                icon = QtGui.QIcon.fromTheme(self.icon)
            else:
                icon = self.icon
            action.setIcon(icon)
        menu.addAction(action)


class Menu(object):

    def __init__(self, label, items):
        self.label = label
        self.items = items

    def append_to(self, menu, parent):
        submenu = menu.addMenu(self.label)
        extend(parent, submenu, self.items)


class Separator(object):

    @classmethod
    def append_to(cls, menu, parent):
        menu.addSeparator()


def extend(parent, menu, items):
    """Append menu items to menu."""
    for item in items:
        item.append_to(menu, parent)
