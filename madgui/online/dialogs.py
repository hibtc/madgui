"""
Dialog for selecting DVM parameters to be synchronized.
"""

from madgui.qt import QtGui
from madgui.core.unit import change_unit, get_raw_label
from madgui.util.layout import VBoxLayout
from madgui.widget.tableview import TableView, ColumnInfo
from madgui.widget.params import export_params


class ListSelectWidget(QtGui.QWidget):

    """
    Widget for selecting from an immutable list of items.
    """

    # TODO: use CheckedStringValue to let user select which items to
    # import/export.

    _headline = 'Select desired items:'

    def __init__(self, columns, headline):
        """Create sizer with content area, i.e. input fields."""
        super().__init__()
        self.grid = grid = TableView(columns=columns, context=self)
        label = QtGui.QLabel(headline)
        self.setLayout(VBoxLayout([label, grid]))

    @property
    def data(self):
        return list(self.grid.rows)

    @data.setter
    def data(self, data):
        self.grid.rows = data


class SyncParamItem:

    def __init__(self, param, dvm_value, mad_value):
        self.param = param
        self.name = param.name
        self.unit = get_raw_label(param.ui_unit)
        self.dvm_value = change_unit(dvm_value, param.unit, param.ui_unit)
        self.mad_value = change_unit(mad_value, param.unit, param.ui_unit)


class SyncParamWidget(ListSelectWidget):

    """
    Dialog for selecting DVM parameters to be synchronized.
    """

    columns = [
        ColumnInfo("Param", 'name'),
        ColumnInfo("DVM value", 'dvm_value'),
        ColumnInfo("MAD-X value", 'mad_value'),
        ColumnInfo("Unit", 'unit',
                   resize=QtGui.QHeaderView.ResizeToContents),
    ]

    def __init__(self, title, headline):
        super().__init__(self.columns, headline)
        self.title = title

    @property
    def exporter(self):
        return self

    def exportTo(self, filename):
        export_params(filename, self.data, data_key='globals')

    exportFilters = [
        ("YAML file", "*.yml", "*.yaml"),
        ("STR file", "*.str"),
    ]


def ImportParamWidget():
    return SyncParamWidget(
        'Import parameters from DVM',
        'Import selected DVM parameters.')


def ExportParamWidget():
    return SyncParamWidget(
        'Set values in DVM from current sequence',
        'Overwrite selected DVM parameters.')
