# encoding: utf-8
"""
Parameter input dialog as used for :class:`TwissParamsWidget` and
:class:`BeamParamsWidget`.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from collections import OrderedDict

import yaml

from madqt.qt import QtCore, QtGui, Qt

import madqt.widget.tableview as tableview
import madqt.util.filedialog as filedialog
from madqt.core.unit import get_raw_label, strip_unit, units


__all__ = [
    'Bools',
    'Strings',
    'Floats',
    'Matrix',
    'ParamTable',
]


# ParamGroups

class ParamGroup(object):

    """Group of corresponding parameters."""

    def __init__(self, valueType, params):
        """Initialize with names and defaults."""
        self.valueType = valueType
        self._defaults = OrderedDict((k, params[k]) for k in sorted(params))

    def names(self):
        """Get all parameter names in this group."""
        return self._defaults.keys()

    def default(self, param):
        """Get the default value for a specific parameter name."""
        return self._defaults[param]


def Bools(**params):
    return ParamGroup(tableview.BoolValue, params)


def Strings(**params):
    return ParamGroup(tableview.QuotedStringValue, params)


def Floats(**params):
    return ParamGroup(tableview.FloatValue, params)


def Matrix(**params):
    """
    Initialize from the given matrix definition.

    Implicitly assumes that len(kwargs) == 1 and the value is a
    consistent non-empty matrix.
    """
    (key, val), = params.items()
    rows = len(val)
    cols = len(val[0])
    params = {"{}{}{}".format(key, row, col): val[row][col]
              for col in range(cols)
              for row in range(rows)}
    return ParamGroup(tableview.FloatValue, params)


# TODO: def Vector(Float)
# unlike Matrix this represents a single MAD-X parameter of type ARRAY.


class ParamInfo(object):

    def __init__(self, name, valueProxy, unit):
        self.name = tableview.StringValue(name, editable=False)
        self.value = valueProxy
        self._unit = unit
        unit_display = '' if unit is None else get_raw_label(unit)
        self.unit = tableview.StringValue(unit_display, editable=False)

    @property
    def quantity(self):
        value = self.value.value
        unit = self._unit
        if value is None or unit is None:
            return value
        return units.Quantity(value, unit)


class ParamTable(tableview.TableView):

    """
    Input controls to show and edit key-value pairs.

    The parameters are displayed in 3 columns: name / value / unit.

    :ivar UnitConverter utool: tool to add/remove units from input values
    :ivar list params: all possible ParamGroups
    :ivar dict data: initial/final parameter values
    """

    data_key = ''

    def __init__(self, spec, utool, *args, **kwargs):
        """Initialize data."""

        self.utool = utool
        self.units = utool._units
        self.params = OrderedDict(
            (param, group)
            for group in spec
            for param in group.names())

        columns = [
            tableview.ColumnInfo("Parameter", 'name'),
            tableview.ColumnInfo("Value", 'value'),
            tableview.ColumnInfo("Unit", 'unit'),
        ]

        super(ParamTable, self).__init__(columns, *args, **kwargs)
        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)

        setResizeMode = self._setColumnResizeMode
        setResizeMode(0, QtGui.QHeaderView.ResizeToContents)
        setResizeMode(1, QtGui.QHeaderView.Stretch)
        setResizeMode(2, QtGui.QHeaderView.ResizeToContents)

        self.setSizePolicy(QtGui.QSizePolicy.Preferred,
                           QtGui.QSizePolicy.Preferred)

    @property
    def _setColumnResizeMode(self):
        header = self.horizontalHeader()
        try:
            return header.setResizeMode
        except AttributeError:  # PyQt5
            return header.setSectionResizeMode

    def data(self):
        """Get dictionary with all input values from dialog."""
        return {row.name.value: row.quantity
                for row in self.rows
                if row.value.value is not None}

    def setData(self, data):
        """Update dialog with initial values."""
        # iterating over `params` (rather than `data`) enforces a particular
        # order in the GUI:
        self.rows = [self.makeParamInfo(param, data.get(param))
                     for param, group in self.params.items()]
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
        unit = self.units.get(param)
        group = self.params[param]
        value = strip_unit(quantity, unit)
        proxy = group.valueType(value, default=group.default(param))
        return ParamInfo(param, proxy, unit)

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

    exportFilters = filedialog.make_filter([
        ("YAML file", "*.yml", "*.yaml"),
        ("JSON file", "*.json"),
    ])

    importFilters = filedialog.make_filter([
        ("YAML file", "*.yml", "*.yaml"),
    ])

    def importFrom(self, filename):
        """Import data from JSON/YAML file."""
        with open(filename, 'rt') as f:
            # Since JSON is a subset of YAML there is no need to invoke a
            # different parser (unless we want to validate the file):
            raw_data = yaml.safe_load(f)
        if self.data_key:
            raw_data = raw_data[self.data_key]
        data = self.utool.dict_add_unit(raw_data)
        self.SetData(data)

    def exportTo(self, filename):
        """Export parameters to YAML file."""
        data = self.data()
        raw_data = self.utool.dict_strip_unit(data)
        if self.data_key:
            raw_data = {self.data_key: raw_data}
        with open(filename, 'wt') as f:
            yaml.safe_dump(raw_data, f, default_flow_style=False)
