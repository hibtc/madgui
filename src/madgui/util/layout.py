"""
Utility functions to deal with layouts.
"""

__all__ = [
    'VBoxLayout',
    'HBoxLayout',
]

from PyQt5 import QtWidgets


class Spacing(int):
    """Fixed pixel spacing for QLayout."""


class Stretch(int):
    """Stretch spacer for QLayout."""


class Strut(int):
    """Strut for QLayout."""


transposed_direction = {
    QtWidgets.QBoxLayout.LeftToRight: QtWidgets.QBoxLayout.TopToBottom,
    QtWidgets.QBoxLayout.RightToLeft: QtWidgets.QBoxLayout.BottomToTop,
    QtWidgets.QBoxLayout.TopToBottom: QtWidgets.QBoxLayout.LeftToRight,
    QtWidgets.QBoxLayout.BottomToTop: QtWidgets.QBoxLayout.RightToLeft,
}


def addItem(layout, item):
    if isinstance(item, tuple):
        item, args = item[0], item[1:]
    else:
        args = ()
    if isinstance(item, QtWidgets.QWidget):
        layout.addWidget(item, *args)
    elif isinstance(item, QtWidgets.QLayout):
        layout.addLayout(item)
    elif isinstance(item, QtWidgets.QSpacerItem):
        layout.addSpacerItem(item)
    elif isinstance(item, QtWidgets.QLayoutItem):
        layout.addItem(item)
    elif isinstance(item, Spacing):
        layout.addSpacing(item)
    elif isinstance(item, Stretch):
        layout.addStretch(item)
    elif isinstance(item, Strut):
        layout.addStrut(item)
    elif isinstance(item, list):
        direction = transposed_direction[layout.direction()]
        sublayout = addItems(QtWidgets.QBoxLayout(direction), item)
        layout.addLayout(sublayout)
    else:
        raise NotImplementedError("Unsupported layout item: {!r}"
                                  .format(item))


def addItems(layout, items, tight=False):
    for item in items:
        addItem(layout, item)
    if tight:
        layout.setContentsMargins(0, 0, 0, 0)
    return layout


def VBoxLayout(items, tight=False):
    return addItems(QtWidgets.QVBoxLayout(), items, tight=tight)


def HBoxLayout(items, tight=False):
    return addItems(QtWidgets.QHBoxLayout(), items, tight=tight)
