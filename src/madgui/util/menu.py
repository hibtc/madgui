"""
Menu creation utilities.
"""

__all__ = [
    'Item',
    'Menu',
    'Separator',
    'extend',
]

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QStyle


class Item:

    def __init__(self, label, shortcut, description, callback, icon=None,
                 enabled=True, checked=None):
        self.label = label
        self.shortcut = shortcut
        self.description = description
        # NOTE: the extra lambda is required to prevent deletion of bound
        # methods upon disabling the action in PyQt4.
        self.callback = lambda: callback()
        self.icon = icon
        self.enabled = enabled
        self.checked = checked

    def action(self, parent):
        checkable = self.checked is not None
        action = QAction(self.label, parent, checkable=checkable)
        if self.shortcut is not None:
            action.setShortcut(self.shortcut)
            action.setShortcutContext(Qt.ApplicationShortcut)
        if self.description is not None:
            action.setStatusTip(self.description)
        if self.callback is not None:
            action.triggered.connect(self.callback)
        if self.icon is not None:
            if isinstance(self.icon, QStyle.StandardPixmap):
                icon = parent.style().standardIcon(self.icon)
            elif isinstance(self.icon, str):
                icon = QIcon.fromTheme(self.icon)
            else:
                icon = self.icon
            action.setIcon(icon)
        _set_from(action.setEnabled, self.enabled)
        _set_from(action.setChecked, self.checked)
        return action

    def append_to(self, menu, parent=None):
        action = self.action(parent)
        menu.addAction(action)
        return action


def _set_from(slot, val):
    if val is not None:
        try:
            cur = val()
            val.changed.connect(slot)
        except TypeError:
            cur = val
        slot(cur)


class Menu:

    def __init__(self, label, items):
        self.label = label
        self.items = items

    def append_to(self, menu, parent):
        submenu = menu.addMenu(self.label)
        extend(parent, submenu, self.items)
        return submenu


class Separator:

    @classmethod
    def append_to(cls, menu, parent):
        return menu.addSeparator()


def extend(parent, menu, items):
    """Append menu items to menu."""
    return [item.append_to(menu, parent)
            for item in items
            if item is not None]
