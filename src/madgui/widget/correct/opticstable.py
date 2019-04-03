
from functools import partial

from PyQt5.QtWidgets import QWidget, QAbstractItemView

from madgui.util.qt import load_ui
from madgui.util.unit import change_unit, get_raw_label
from madgui.widget.tableview import TableItem, delegates


class OpticsTable(QWidget):

    num_focus_levels = 6

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        load_ui(self, __package__, 'opticstable.ui')
        self.opticsTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.opticsTable.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.readFocusButton.clicked.connect(self.read_focus)

    def setEnabled(self, enabled):
        self.read1stFocusComboBox.setEnabled(enabled)
        self.read2ndFocusComboBox.setEnabled(enabled)
        self.readFocusButton.setEnabled(enabled)

    def set_corrector(self, corrector):
        self.corrector = corrector
        self.opticsTable.set_viewmodel(self.get_optic_row, corrector.optics)
        self.corrector.optics.update_finished.connect(self.on_optics_updated)

        focus_choices = [
            "F{}".format(i+1)
            for i in range(self.num_focus_levels)
        ]
        self.read1stFocusComboBox.addItems(focus_choices)
        self.read2ndFocusComboBox.addItems(focus_choices)
        self.read1stFocusComboBox.setCurrentText("F1")
        self.read2ndFocusComboBox.setCurrentText("F4")

    def get_optic_row(self, i, o) -> ("#", "kL (1)", "kL (2)"):
        return [
            TableItem(i+1),
        ] + [
            TableItem(change_unit(o[par.lower()], info.unit, info.ui_unit),
                      set_value=partial(self.set_optic_value, par),
                      delegate=delegates[float])
            for par in self.corrector.selected['optics']
            for info in [self.corrector.optic_params[i]]
        ]

    def set_optic_value(self, par, i, o, value):
        o[par.lower()] = value

    def read_focus(self):
        """Update focus level and automatically load QP values."""
        foci = [self.read1stFocusComboBox.currentIndex()+1,
                self.read2ndFocusComboBox.currentIndex()+1]

        corr = self.corrector
        ctrl = corr.control
        # TODO: this should be done with a more generic API
        # TODO: do this without beamoptikdll to decrease the waiting time
        acs = ctrl.backend.beamoptikdll
        values, channels = acs.GetMEFIValue()
        vacc = acs.GetSelectedVAcc()
        try:
            optics = []
            for focus in foci:
                acs.SelectMEFI(vacc, *channels._replace(focus=focus))
                optics.append({
                    par.lower(): ctrl.read_param(par)
                    for par in corr.selected['optics']
                })
            corr.optics[:] = optics
        finally:
            acs.SelectMEFI(vacc, *channels)

    def on_optics_updated(self, *_):
        self.opticsTable.model().titles[1:] = [
            "{}/{}".format(info.name, get_raw_label(info.ui_unit))
            for info in self.corrector.optic_params
        ]
