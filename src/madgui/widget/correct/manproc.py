from PyQt5.QtCore import pyqtSlot as slot
from PyQt5.QtWidgets import QWidget

from madgui.util.qt import load_ui


class ManProcWidget(QWidget):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        load_ui(self, __package__, 'manproc.ui')

    def set_corrector(self, corrector):
        self.corrector = corrector
        self.corrector.optics.update_finished.connect(self.on_optics_updated)
        self.on_optics_updated()

    def on_optics_updated(self, *_):
        num_optics = len(self.corrector.optics)
        if num_optics == self.opticComboBox.count():
            return
        selected = self.opticComboBox.currentIndex()
        self.opticComboBox.clear()
        self.opticComboBox.addItems([
            "Optic {}".format(i+1)
            for i in range(num_optics)
        ])
        self.opticComboBox.setCurrentIndex(min(selected, num_optics-1))
        self.setOpticButton.setEnabled(num_optics > 0)

    @slot()
    def on_recordButton_clicked(self):
        self.corrector.add_record(
            self.opticComboBox.currentIndex(), None)

    @slot()
    def on_setOpticButton_clicked(self):
        # TODO: disable "write" button until another optic has been selected
        # or the optic has changed in the ACS
        self.corrector.set_optic(self.opticComboBox.currentIndex())
