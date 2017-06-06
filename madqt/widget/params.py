# encoding: utf-8
"""
Parameter input dialog.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from collections import OrderedDict

from six import string_types as basestring
import yaml

from madqt.qt import QtCore, QtGui, Qt

import madqt.widget.tableview as tableview
from madqt.core.unit import get_raw_label, strip_unit


__all__ = [
    'ParamSpec',
    'ParamTable',
]


class ParamSpec(object):

    """Input parameter specification."""

    def __init__(self, name, value, editable=True):
        self.name = name
        self.value = value
        self.editable = editable

    def value_type(self):
        if isinstance(self.value, bool):
            return tableview.BoolValue
        if isinstance(self.value, (int, float)):
            return tableview.QuantityValue
        if isinstance(self.value, (basestring)):
            return tableview.QuotedStringValue
        # TODO: list -> VectorValue (single MAD-X parameter of type ARRAY)
        raise ValueError("Unknown parameter type: {}={}"
                         .format(self.name, self.value))


class ParamInfo(object):

    """Internal parameter description for the TableView."""

    def __init__(self, name, valueProxy):
        self.name = name
        self._value = valueProxy

    @property
    def value(self):
        return self._value.value


class ParamTable(tableview.TableView):

    """
    Input controls to show and edit key-value pairs.

    The parameters are displayed in 3 columns: name / value / unit.

    :ivar UnitConverter utool: tool to add/remove units from input values
    :ivar list params: all possible ParamGroups
    :ivar dict data: initial/final parameter values
    """

    # TODO: visually indicate rows with default or unset values (gray)
    # TODO: move rows with default or unset values to bottom?

    data_key = ''

    def __init__(self, spec, utool, **kwargs):
        """Initialize data."""

        self.utool = utool
        self.units = utool._units
        self.params = OrderedDict((param.name, param) for param in spec)

        columns = [
            tableview.ColumnInfo("Parameter", 'name'),
            tableview.ColumnInfo("Value", '_value'),
        ]

        super(ParamTable, self).__init__(columns=columns, **kwargs)
        # configure the header's selection behaviour in case anyone turns on
        # the horizontalHeader again:
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().hide()
        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)

        self.setSizePolicy(QtGui.QSizePolicy.Preferred,
                           QtGui.QSizePolicy.Preferred)

    def data(self):
        """Get dictionary with all input values from dialog."""
        return {row.name: row.value
                for row in self.rows
                if row.value is not None}

    def setData(self, data):
        """Update dialog with initial values."""
        # iterating over `params` (rather than `data`) enforces a particular
        # order in the GUI:
        self.rows = [self.makeParamInfo(param, data.get(param))
                     for param in self.params]
        self.selectRow(0)
        # Set initial size:
        if not self.isVisible():
            self.updateGeometries()

    def sizeHintForColumn(self, column):
        baseValue = super(ParamTable, self).sizeHintForColumn(column)
        if column == 1:
            return baseValue + 50
        return baseValue

    def makeParamInfo(self, param, quantity):
        # TODO: use UI units
        unit = self.units.get(param)
        param = self.params[param]
        default = param.value
        if unit is not None:
            default = param.value * unit
        textcolor = Qt.black if param.editable else Qt.darkGray
        proxy = param.value_type()(quantity, default=default,
                                   editable=param.editable,
                                   textcolor=textcolor)
        return ParamInfo(param.name, proxy)

    def keyPressEvent(self, event):
        """<Enter>: open editor; <Delete>/<Backspace>: remove value."""
        if self.state() == QtGui.QAbstractItemView.NoState:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.setRowValue(self.curRow(), None)
                event.accept()
                return
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.edit(self.model().index(self.curRow(), 1))
                event.accept()
                return
        super(ParamTable, self).keyPressEvent(event)

    def curRow(self):
        # This is failsafe only in SingleSelection widgets:
        return self.selectedIndexes()[0].row()

    def setRowValue(self, row, value):
        """Set the value of the parameter in the specified row."""
        model = self.model()
        index = model.index(row, 1)
        model.setData(index, value)
        model.dataChanged.emit(index, index)

    # data im-/export

    exportFilters = [
        ("YAML file", "*.yml", "*.yaml"),
        ("JSON file", "*.json"),
    ]

    importFilters = [
        ("YAML file", "*.yml", "*.yaml"),
    ]

    def importFrom(self, filename):
        """Import data from JSON/YAML file."""
        with open(filename, 'rt') as f:
            # Since JSON is a subset of YAML there is no need to invoke a
            # different parser (unless we want to validate the file):
            raw_data = yaml.safe_load(f)
        if self.data_key:
            raw_data = raw_data[self.data_key]
        data = self.utool.dict_add_unit(raw_data)
        self.setData(data)

    def exportTo(self, filename):
        """Export parameters to YAML file."""
        data = self.data()
        raw_data = self.utool.dict_strip_unit(data)
        if self.data_key:
            raw_data = {self.data_key: raw_data}
        with open(filename, 'wt') as f:
            yaml.safe_dump(raw_data, f, default_flow_style=False)
