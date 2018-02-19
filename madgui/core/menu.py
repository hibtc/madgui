"""
Menu creation utilities.
"""

from madgui.qt import QtGui


__all__ = [
    'Item',
    'Menu',
    'Separator',
    'extend',
]


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
        action = QtGui.QAction(self.label, parent, checkable=checkable)
        if self.shortcut is not None:
            action.setShortcut(self.shortcut)
        if self.description is not None:
            action.setStatusTip(self.description)
        if self.callback is not None:
            action.triggered.connect(self.callback)
        if self.icon is not None:
            if isinstance(self.icon, QtGui.QStyle.StandardPixmap):
                icon = parent.style().standardIcon(self.icon)
            elif isinstance(self.icon, str):
                icon = QtGui.QIcon.fromTheme(self.icon)
            else:
                icon = self.icon
            action.setIcon(icon)
        if self.enabled is not None:
            self._dynamic_property(self.enabled, action.setEnabled)
        if checkable:
            self._dynamic_property(self.checked, action.setChecked)
        return action

    def append_to(self, menu, parent=None):
        menu.addAction(self.action(parent))

    def _dynamic_property(self, prop, setter):
        try:
            cur = prop.value
            prop.changed.connect(setter)
        except AttributeError:
            cur = prop
        setter(cur)


class Menu:

    def __init__(self, label, items):
        self.label = label
        self.items = items

    def append_to(self, menu, parent):
        submenu = menu.addMenu(self.label)
        extend(parent, submenu, self.items)


class Separator:

    @classmethod
    def append_to(cls, menu, parent):
        menu.addSeparator()


def extend(parent, menu, items):
    """Append menu items to menu."""
    for item in items:
        if item is not None:
            item.append_to(menu, parent)
