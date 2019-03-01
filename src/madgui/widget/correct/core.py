import numpy as np

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QAbstractItemView

from madgui.util.unit import change_unit, get_raw_label
from madgui.util.qt import bold
from madgui.widget.tableview import TableItem, delegates, TableView

from madgui.online.procedure import Target


class MonitorTable(TableView):

    """TableView widget that shows the current monitor readouts of an orbit
    correction procedure and updates automatically."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def set_corrector(self, corrector):
        self.set_viewmodel(
            self.get_readout_row, corrector.readouts, unit=True)

    def get_readout_row(self, i, r) -> ("Monitor", "X", "Y"):
        return [
            TableItem(r.name),
            TableItem(r.posx, name='posx'),
            TableItem(r.posy, name='posy'),
        ]


class TargetTable(TableView):

    """TableView widget that shows the target monitor X/Y constraints of an
    orbit correction procedure and allows the user to change them."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def set_corrector(self, corrector):
        self.corrector = corrector
        self.set_viewmodel(
            self.get_cons_row, corrector.targets, unit=True)

    def get_cons_row(self, i, t) -> ("Target", "X", "Y"):
        mode = self.corrector.mode
        active_x = 'x' in mode
        active_y = 'y' in mode
        textcolor = QColor(Qt.darkGray), QColor(Qt.black)
        return [
            TableItem(t.elem),
            TableItem(t.x, name='x', set_value=self.set_x_value,
                      editable=active_x, foreground=textcolor[active_x],
                      delegate=delegates[float]),
            TableItem(t.y, name='y', set_value=self.set_y_value,
                      editable=active_y, foreground=textcolor[active_y],
                      delegate=delegates[float]),
        ]

    def set_x_value(self, i, t, value):
        self.corrector.targets[i] = Target(t.elem, value, t.y)

    def set_y_value(self, i, t, value):
        self.corrector.targets[i] = Target(t.elem, t.x, value)


class ResultTable(TableView):

    """TableView widget that shows the fit results (i.e. steerer angles) of an
    orbit correction procedure and allows the user to change them."""

    # TODO: make 'optimal'-column in resultsTable editable and update
    #       self.applyButton.setEnabled according to its values

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def set_corrector(self, corrector):
        self.corrector = corrector
        self.set_viewmodel(self.get_steerer_row, corrector.variables)

    def get_steerer_row(self, i, v) -> ("Steerer", "Now", "To Be", "Unit"):
        initial = self.corrector.online_optic.get(v.lower())
        matched = self.corrector.saved_optics().get(v.lower())
        changed = matched is not None and not np.isclose(initial, matched)
        style = {
            # 'foreground': QColor(Qt.red),
            'font': bold(),
        } if changed else {}
        info = self.corrector._knobs[v.lower()]
        return [
            TableItem(v),
            TableItem(change_unit(initial, info.unit, info.ui_unit)),
            TableItem(change_unit(matched, info.unit, info.ui_unit),
                      set_value=self.set_steerer_value,
                      delegate=delegates[float], **style),
            TableItem(get_raw_label(info.ui_unit)),
        ]

    def set_steerer_value(self, i, v, value):
        info = self.corrector._knobs[v.lower()]
        value = change_unit(value, info.ui_unit, info.unit)
        results = self.corrector.saved_optics().copy()
        if results[v.lower()] != value:
            results[v.lower()] = value
            self.corrector.saved_optics.push(results)
