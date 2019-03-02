import numpy as np
from PyQt5.QtWidgets import QWidget, QAbstractItemView

from madgui.util.qt import load_ui
from madgui.widget.tableview import TableItem


class RecordsTable(QWidget):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        load_ui(self, __package__, 'recordstable.ui')
        self.recordsTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.recordsTable.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def set_corrector(self, corrector):
        self.corrector = corrector
        self.recordsTable.set_viewmodel(
            self.get_record_row, corrector.records, unit=True)
        self.recordsTable.connectRemoveButton(self.removeRecordsButton)
        self.recordsTable.connectClearButton(self.clearRecordsButton)

    def get_record_row(self, i, r) -> ("Optic", "Monitor", "X", "Y"):
        return [
            TableItem(self.get_optic_name(r)),
            TableItem(r.monitor),
            TableItem(r.readout.posx, name='posx'),
            TableItem(r.readout.posy, name='posx'),
        ]

    def get_optic_name(self, record):
        for i, optic in enumerate(self.corrector.optics):
            if all(np.isclose(record.optics[k.lower()], v)
                    for k, v in optic.items()):
                return "Optic {}".format(i+1)
        return "custom optic"
