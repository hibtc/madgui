"""
Dialog for selecting ACS parameters to be synchronized.
"""

__all__ = [
    'SyncParamItem',
    'SyncParamWidget',
    'ImportParamWidget',
    'ExportParamWidget',
]

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QLabel, QWidget

from madgui.util.unit import change_unit, get_raw_label
from madgui.util.layout import VBoxLayout
from madgui.util.qt import bold
from madgui.widget.tableview import TableView, TableItem
from madgui.widget.params import export_params


class SyncParamItem:

    def __init__(self, param, acs_value, mad_value):
        self.param = param
        self.name = param.name
        self.unit = get_raw_label(param.ui_unit)
        self.acs_value = change_unit(acs_value, param.unit, param.ui_unit)
        self.mad_value = change_unit(mad_value, param.unit, param.ui_unit)


class SyncParamWidget(QWidget):

    """
    Dialog for selecting ACS parameters to be synchronized.
    """

    # TODO: use CheckedStringValue to let user select which items to
    # import/export.

    def get_row(self, i, p) -> ("Param", "ACS value", "MAD-X value", "Unit"):
        style = [{}, {
            'font': bold(),
            'backgroundColor': QColor(Qt.gray),
        } if p.acs_value != p.mad_value else {}]
        return [
            TableItem(p.name),
            TableItem(p.acs_value, **style['acs' in self.highlight]),
            TableItem(p.mad_value, **style['mad' in self.highlight]),
            TableItem(p.unit),
        ]

    def __init__(self, title, headline, highlight=''):
        """Create sizer with content area, i.e. input fields."""
        super().__init__()
        self.grid = TableView()
        self.grid.set_viewmodel(self.get_row)
        self.highlight = highlight
        self.title = title
        label = QLabel(headline)
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
        'Import parameters from ACS',
        'Import selected ACS parameters.', 'acs')


def ExportParamWidget():
    return SyncParamWidget(
        'Set values in ACS from current sequence',
        'Overwrite selected ACS parameters.', 'mad')
