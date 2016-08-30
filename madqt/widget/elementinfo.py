# encoding: utf-8
"""
Info boxes to display element detail.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import madqt.widget.tableview as tableview
import madqt.core.unit as unit


__all__ = [
    'ElementInfoBox',
]


def _format_key(item):
    return item[0]


def _format_val(item):
    val = item[1]
    if isinstance(val, list):
        return '[{}]'.format(
            ", ".join(_format_val((None, v)) for v in val)
        )
    elif isinstance(val, (float, unit.units.Quantity)):
        return unit.format_quantity(val, '.3f')
    elif isinstance(val, basestring):
        return val
    else:
        return str(val)


class ElementInfoBox(tableview.TableView):

    columns = [
        tableview.ColumnInfo('Parameter', _format_key),
        tableview.ColumnInfo('Value', _format_val),
    ]

    def __init__(self, segment, el_name, *args, **kwargs):
        super(ElementInfoBox, self).__init__(self.columns, *args, **kwargs)

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

        el = self.element
        rows = list(el.items())

        # convert to title case:
        rows = [(k.title(), v) for (k, v) in rows]

        # presort alphanumerically:
        # (with some luck the order on the elements with equal key in the
        # subsequent sort will be left invariant)
        rows = sorted(rows)

        # sort preferred elements to top:
        order = [
            'Name',
            'Type',
            'At',
            'L',
            'Ksl',
            'Knl',
        ]
        order = {k: i for i, k in enumerate(order)}
        rows = sorted(rows, key=lambda row: order.get(row[0], len(order)))
        rows = [row for row in rows if row[0] != 'Vary']

        # update view:
        self.rows = rows

        self.resizeColumnsToContents()
