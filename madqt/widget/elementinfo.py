# encoding: utf-8
"""
Info boxes to display element detail.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from madqt.qt import QtCore, QtGui

from madqt.widget.tableview import TableView, ColumnInfo


__all__ = [
    'ElementInfoBox',
]


def makeIndex(values):
    return {k: i for i, k in enumerate(values)}


class ParamInfo(object):

    def __init__(self, name, value):
        self.name = name
        self.value = value

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


class ElementInfoBox(TableView):

    columns = [
        ColumnInfo('Parameter', 'name'),
        ColumnInfo('Value', 'value'),
    ]

    def __init__(self, segment, el_name, *args, **kwargs):
        super(ElementInfoBox, self).__init__(self.columns, *args, **kwargs)

        self.horizontalHeader().hide()

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
        return self.segment.get_element_data(
            self.segment.get_element_info(self.el_name).index)

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
