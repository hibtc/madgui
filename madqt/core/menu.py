# encoding: utf-8
"""
Menu creation utilities.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from PyQt4 import QtCore, QtGui


__all__ = [
    'Item',
    'CondItem',
    'Menu',
    'Separator',
    'extend',
]


class Item(object):

    def __init__(self, label, shortcut, description, action):
        self.label = label
        self.shortcut = shortcut
        self.description = description
        self.action = action

    def append_to(self, menu, parent=None):
        if parent is None:
            parent = menu
        action = QtGui.QAction(self.label, parent)
        if self.shortcut is not None:
            action.setShortcut(self.shortcut)
        if self.description is not None:
            action.setStatusTip(self.description)
        if self.action is not None:
            action.triggered.connect(self.action)
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
