import logging

from PyQt5.QtCore import pyqtSlot as slot
from PyQt5.QtWidgets import QWidget

from madgui.util.qt import load_ui
from madgui.online.procedure import ProcBot


class AutoProcWidget(QWidget):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        load_ui(self, __package__, 'autoproc.ui')

    def set_corrector(self, corrector):
        self.corrector = corrector
        self.bot = ProcBot(self, corrector)

    # callback API for ProcBot:

    def update_fit(self):
        self.corrector.update_fit()

    def update_ui(self):
        running = self.bot.running
        self.numIgnoredSpinBox.setEnabled(not running)
        self.numUsedSpinBox.setEnabled(not running)
        self.startProcedureButton.setEnabled(not running)
        self.abortProcedureButton.setEnabled(running)
        self.progressBar.setRange(0, self.bot.totalops)
        self.progressBar.setValue(self.bot.progress)

    def set_progress(self, progress):
        self.progressBar.setValue(progress)

    def log(self, text, *args, **kwargs):
        formatted = text.format(*args, **kwargs)
        logging.info(formatted)
        self.logEdit.appendPlainText(formatted)

    # event handlers:

    @slot()
    def on_startProcedureButton_clicked(self):
        self.bot.start(
            self.numIgnoredSpinBox.value(),
            self.numUsedSpinBox.value())

    @slot()
    def on_abortProcedureButton_clicked(self):
        self.bot.cancel()

    def closeEvent(self, event):
        self.bot.cancel()
        super().closeEvent(event)
