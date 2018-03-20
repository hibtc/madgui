"""
Dialog for selecting DVM parameters to be synchronized.
"""

from madgui.qt import QtGui
from madgui.core.unit import to_ui, ui_units
from madgui.util.layout import VBoxLayout
from madgui.widget.tableview import TableView, ColumnInfo


class ListSelectWidget(QtGui.QWidget):

    """
    Widget for selecting from an immutable list of items.
    """

    _headline = 'Select desired items:'

    # TODO: allow to customize initial selection
    # FIXME: select-all looks ugly, check/uncheck-each is tedious...

    def __init__(self, columns, headline):
        """Create sizer with content area, i.e. input fields."""
        super().__init__()
        self.grid = grid = TableView(columns=columns)
        label = QtGui.QLabel(headline)
        self.setLayout(VBoxLayout([label, grid]))

    @property
    def data(self):
        return list(self.grid.rows)

    @data.setter
    def data(self, data):
        self.grid.rows = data
        # TODO: replace SELECT(ALL) by SELECT(SELECTED)
        # TODO: the following was disabled for convenience. Currently, the
        # selection is not even used from the client code!
        #for idx in range(len(data)):
        #    self.grid.Select(idx)


class SyncParamItem:

    def __init__(self, param, dvm_value, mad_value, attr):
        self.param = param
        self.name = param.name
        self.unit = ui_units.label(attr)
        self.dvm_value = to_ui(attr, dvm_value)
        self.mad_value = to_ui(attr, mad_value)


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


def ImportParamWidget():
    return SyncParamWidget(
        'Import parameters from DVM',
        'Import selected DVM parameters.')


def ExportParamWidget():
    return SyncParamWidget(
        'Set values in DVM from current sequence',
        'Overwrite selected DVM parameters.')


class MonitorItem:

    def __init__(self, el_name, values):
        self.name = el_name
        self.posx = to_ui('x', values.get('posx'))
        self.posy = to_ui('x', values.get('posy'))
        self.envx = to_ui('x', values.get('envx'))
        self.envy = to_ui('x', values.get('envy'))
        self.unit = ui_units.label('x')


class MonitorWidget(ListSelectWidget):

    """
    Dialog for selecting SD monitor values to be imported.
    """

    title = 'Set values in DVM from current sequence'
    headline = "Import selected monitor measurements:"

    columns = [
        ColumnInfo("Monitor", 'name'),
        ColumnInfo("x", 'posx'),
        ColumnInfo("y", 'posy'),
        ColumnInfo("x width", 'envx'),
        ColumnInfo("y width", 'envy'),
        ColumnInfo("Unit", 'unit', resize=QtGui.QHeaderView.ResizeToContents),
    ]

    def __init__(self):
        super().__init__(self.columns, self.headline)
