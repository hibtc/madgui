from PyQt5.QtCore import pyqtSlot as slot
from PyQt5.QtWidgets import QWidget

from madgui.util.qt import load_ui


class FitSettingsWidget(QWidget):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        load_ui(self, __package__, 'fitsettings.ui')

    def set_corrector(self, corrector):
        self.corrector = corrector
        self.corrector.setup_changed.connect(self.on_setup_changed)

    # button events

    @slot()
    def on_methodMatchButton_clicked(self):
        self.corrector.strategy.set('match')

    @slot()
    def on_methodORMButton_clicked(self):
        self.corrector.strategy.set('orm')

    @slot()
    def on_methodSectormapButton_clicked(self):
        self.corrector.strategy.set('tm')

    @slot()
    def on_backtrackCheckBox_clicked(self):
        self.corrector.use_backtracking.set(
            self.backtrackCheckBox.isChecked())

    def on_setup_changed(self):
        if self.corrector.knows_targets_readouts():
            self.backtrackCheckBox.setEnabled(True)
        else:
            self.backtrackCheckBox.setEnabled(False)
            self.backtrackCheckBox.setChecked(True)
