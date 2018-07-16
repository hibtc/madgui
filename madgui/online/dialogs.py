"""
Dialog for selecting DVM parameters to be synchronized.
"""

from madgui.qt import QtGui
from madgui.core.unit import change_unit, get_raw_label
from madgui.util.layout import VBoxLayout
from madgui.util.qt import bold
from madgui.widget.tableview import TableView, TableItem
from madgui.widget.params import export_params


class SyncParamItem:

    def __init__(self, param, dvm_value, mad_value):
        self.param = param
        self.name = param.name
        self.unit = get_raw_label(param.ui_unit)
        self.dvm_value = change_unit(dvm_value, param.unit, param.ui_unit)
        self.mad_value = change_unit(mad_value, param.unit, param.ui_unit)


class SyncParamWidget(QtGui.QWidget):

    """
    Dialog for selecting DVM parameters to be synchronized.
    """

    # TODO: use CheckedStringValue to let user select which items to
    # import/export.

    def get_row(self, i, p) -> ("Param", "DVM value", "MAD-X value", "Unit"):
        style = {
            'font': bold(),
            # apparently `backgroundColor` doesn't work with TreeView if also
            # using style sheets:
            # 'backgroundColor': QtGui.QColor(Qt.red),
        } if p.dvm_value != p.mad_value else {}
        return [
            TableItem(p.name, **style),
            TableItem(p.dvm_value, **style),
            TableItem(p.mad_value, **style),
            TableItem(p.unit, **style),
        ]

    def __init__(self, title, headline):
        """Create sizer with content area, i.e. input fields."""
        super().__init__()
        self.grid = TableView()
        self.grid.set_rowgetter(self.get_row)
        self.title = title
        label = QtGui.QLabel(headline)
        self.setLayout(VBoxLayout([label, self.grid]))

    @property
    def data(self):
        return list(self.grid.rows)

    @data.setter
    def data(self, data):
        self.grid.rows = data

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
