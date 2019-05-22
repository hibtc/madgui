"""
Utilities for defining a window menu in a more concice notation than manually
creating the ``QMenuItem`` and assigning properties.
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

    """Represents a menu item. Objects of this type will be realized as
    ``QMenuItem``.

    The following properties can be given:

    :ivar str label: menu item label
    :ivar str shortcut: shortcut, e.g. "Ctrl+S" (optional)
    :ivar str description: tooltip and status bar message
    :ivar callable callback: action to be taken when clicking the menu item
    :ivar icon: icon, can be QStyle.StandardPixmap, an icon name defined in
                the theme, or a QIcon
    :ivar Bool enabled: whether the item is enabled (optional)
    :ivar Bool checked: whether the item is checked (optional)
    """

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
        """Create a ``QAction`` from this item."""
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
        """Append this item to the given menu."""
        action = self.action(parent)
        menu.addAction(action)
        return action


def _set_from(slot, val):
    """Connect a :class:`~madgui.util.collections.Bool` to the given slot.
    This is used to keep the state of ``QAction.checked`` and ``.enabled``
    properties synchronized."""
    if val is not None:
        try:
            cur = val()
            val.changed.connect(slot)
        except TypeError:
            cur = val
        slot(cur)


class Menu:

    """(Sub-)menu to be inserted."""

    def __init__(self, label, items):
        self.label = label
        self.items = items

    def append_to(self, menu, parent):
        submenu = menu.addMenu(self.label)
        extend(parent, submenu, self.items)
        return submenu


class Separator:

    """Separator to be inserted in a menu."""

    @classmethod
    def append_to(cls, menu, parent):
        return menu.addSeparator()


def extend(parent, menu, items):
    """Append menu items to menu."""
    return [item.append_to(menu, parent)
            for item in items
            if item is not None]
