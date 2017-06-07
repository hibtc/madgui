"""
Utility functions to deal with layouts.
"""


from __future__ import absolute_import
from __future__ import unicode_literals


from madqt.qt import QtGui


__all__ = [
    'VBoxLayout',
    'HBoxLayout',
]


class Spacing(int): pass
class Stretch(int): pass
class Strut(int): pass


transposed_direction = {
    QtGui.QBoxLayout.LeftToRight: QtGui.QBoxLayout.TopToBottom,
    QtGui.QBoxLayout.RightToLeft: QtGui.QBoxLayout.BottomToTop,
    QtGui.QBoxLayout.TopToBottom: QtGui.QBoxLayout.LeftToRight,
    QtGui.QBoxLayout.BottomToTop: QtGui.QBoxLayout.RightToLeft,
}


def addItem(layout, item):
    if isinstance(item, tuple):
        item, args = item[0], item[1:]
    else:
        args = ()
    if isinstance(item, QtGui.QWidget):
        layout.addWidget(item, *args)
    elif isinstance(item, QtGui.QLayout):
        layout.addLayout(item)
    elif isinstance(item, QtGui.QSpacerItem):
        layout.addSpacerItem(item)
    elif isinstance(item, QtGui.QLayoutItem):
        layout.addItem(item)
    elif isinstance(item, Spacing):
        layout.addSpacing(item)
    elif isinstance(item, Stretch):
        layout.addStretch(item)
    elif isinstance(item, Strut):
        layout.addStrut(item)
    elif isinstance(item, list):
        direction = transposed_direction[layout.direction()]
        sublayout = addItems(QtGui.QBoxLayout(direction), item)
        layout.addLayout(sublayout)
    else:
        raise NotImplementedError("Unsupported layout item: {!r}"
                                  .format(item))


def addItems(layout, items):
    for item in items:
        addItem(layout, item)
    return layout


def VBoxLayout(items):
    return addItems(QtGui.QVBoxLayout(), items)


def HBoxLayout(items):
    return addItems(QtGui.QHBoxLayout(), items)
