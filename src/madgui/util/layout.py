"""
Utility functions to deal with layouts.
"""

__all__ = [
    'VBoxLayout',
    'HBoxLayout',
    'Spacing',
    'Stretch',
    'Strut',

]

from PyQt5.QtWidgets import (
    QBoxLayout, QHBoxLayout, QLayout, QLayoutItem, QSpacerItem,
    QVBoxLayout, QWidget)


class Spacing(int):
    """Fixed pixel spacing for QLayout."""


class Stretch(int):
    """Stretch spacer for QLayout."""


class Strut(int):
    """Strut for QLayout."""


transposed_direction = {
    QBoxLayout.LeftToRight: QBoxLayout.TopToBottom,
    QBoxLayout.RightToLeft: QBoxLayout.BottomToTop,
    QBoxLayout.TopToBottom: QBoxLayout.LeftToRight,
    QBoxLayout.BottomToTop: QBoxLayout.RightToLeft,
}


def addItem(layout, item):
    if isinstance(item, tuple):
        item, args = item[0], item[1:]
    else:
        args = ()
    if isinstance(item, QWidget):
        layout.addWidget(item, *args)
    elif isinstance(item, QLayout):
        layout.addLayout(item)
    elif isinstance(item, QSpacerItem):
        layout.addSpacerItem(item)
    elif isinstance(item, QLayoutItem):
        layout.addItem(item)
    elif isinstance(item, Spacing):
        layout.addSpacing(item)
    elif isinstance(item, Stretch):
        layout.addStretch(item)
    elif isinstance(item, Strut):
        layout.addStrut(item)
    elif isinstance(item, list):
        direction = transposed_direction[layout.direction()]
        sublayout = addItems(QBoxLayout(direction), item)
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
    return addItems(QVBoxLayout(), items, tight=tight)


def HBoxLayout(items, tight=False):
    return addItems(QHBoxLayout(), items, tight=tight)
