# encoding: utf-8
"""
Info boxes to display element detail.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from madqt.qt import QtCore, QtGui

import madqt.widget.tableview as tableview


__all__ = [
    'ElementInfoBox',
]


def makeIndex(values):
    return {k: i for i, k in enumerate(values)}


class ParamInfo(object):

    def __init__(self, name, value):
        self._name = tableview.StringValue(name, editable=False)
        self._value = tableview.makeValue(value, editable=False)

    @property
    def name(self):
        return self._name.value

    @property
    def value(self):
        return self._value.value

    # sort preferred elements to top:
    sortTop = makeIndex([
        'Name',
        'Type',
        'At',
        'L',
        'Ksl',
        'Knl',
    ])

    def sortKey(self):
        return (self.sortTop.get(self.name, len(self.sortTop)),
                self.name, self.value)


class ElementInfoBox(tableview.TableView):

    columns = [
        tableview.ColumnInfo('Parameter', '_name'),
        tableview.ColumnInfo('Value', '_value'),
    ]

    def __init__(self, segment, el_name, *args, **kwargs):
        super(ElementInfoBox, self).__init__(self.columns, *args, **kwargs)

        # control resize behaviour:
        header = self.horizontalHeader()
        header.setResizeMode(0, QtGui.QHeaderView.ResizeToContents)
        header.setResizeMode(1, QtGui.QHeaderView.Stretch)
        header.hide()

        sizePolicy = self.sizePolicy()
        sizePolicy.setVerticalPolicy(QtGui.QSizePolicy.Preferred)
        self.setSizePolicy(sizePolicy)

        self.segment = segment
        self.el_name = el_name

        self.segment.updated.connect(self.update)

    def closeEvent(self, event):
        self.segment.updated.disconnect(self.update)
        event.accept()

    @property
    def el_name(self):
        return self._el_name

    @el_name.setter
    def el_name(self, name):
        self._el_name = name
        self.update()

    @property
    def element(self):
        elements = self.segment.universe.madx.active_sequence.elements
        raw_element = elements[self.el_name]
        return self.segment.utool.dict_add_unit(raw_element)

    def update(self):
        """
        Update the contents of the managed popup window.
        """
        blacklist = {'vary'}
        rows = [ParamInfo(k.title(), v)
                for k, v in self.element.items()
                if k.lower() not in blacklist]
        self.rows = sorted(rows, key=ParamInfo.sortKey)
        self.resizeColumnsToContents()
