"""
Contains a widget for measuring orbit response matrix in an online
environment.
"""

__all__ = [
    'MeasureWidget',
]

import os
import re
import time
import logging

from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QWidget

from madgui.util.qt import load_ui
from madgui.widget.tableview import TableItem, delegates

from madgui.online.procedure import Corrector, ProcBot


class MeasureWidget(QWidget):

    ui_file = 'orm_measure.ui'
    extension = '.orm_measurement.yml'

    def __init__(self, session):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
        self.control = session.control
        self.model = session.model()
        self.corrector = Corrector(session, False)
        self.corrector.setup({
            'monitors': [],
        })
        self.corrector.start()
        self.bot = ProcBot(self, self.corrector)

        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    def sizeHint(self):
        return QSize(600, 400)

    def init_controls(self):
        self.opticsTable.set_viewmodel(self.get_corrector_row)
        self.monitorTable.set_viewmodel(self.get_monitor_row)
        self.view = self.corrector.session.window().open_graph('orbit')

    def set_initial_values(self):
        self.set_folder('.')    # FIXME
        self.fileEdit.setText(
            "{date}_{time}_{sequence}_{monitor}"+self.extension)
        self.d_phi = {}
        self.opticsTable.rows[:] = []
        self.monitorTable.rows[:] = self.corrector.all_monitors
        self.update_ui()

    def connect_signals(self):
        self.folderButton.clicked.connect(self.change_output_file)
        self.startButton.clicked.connect(self.start_bot)
        self.cancelButton.clicked.connect(self.bot.cancel)
        self.monitorTable.selectionModel().selectionChanged.connect(
            self.monitor_selection_changed)
        self.filterEdit.textChanged.connect(lambda _: self._update_knobs())
        self.defaultSpinBox.valueChanged.connect(
            lambda _: self.opticsTable.rows.touch())

    def get_monitor_row(self, i, m) -> ("Monitor",):
        return [
            TableItem(m),
        ]

    def get_corrector_row(self, i, c) -> ("Param", "Δ"):
        default = self.defaultSpinBox.value() or None
        return [
            TableItem(c.name),
            TableItem(
                self.d_phi.get(c.name.lower(), default),
                set_value=self.set_delta,
                delegate=delegates[float]),
        ]

    def set_delta(self, i, c, value):
        self.d_phi[c.name.lower()] = value

    def monitor_selection_changed(self, selected, deselected):
        self.corrector.setup({
            'monitors': [
                self.corrector.all_monitors[idx.row()]
                for idx in self.monitorTable.selectedIndexes()
            ],
        })
        self._update_knobs()
        self.update_ui()

    def _update_knobs(self):
        match = self._get_filter()
        if not match:
            return
        elements = self.model.elements
        last_mon = elements.index(self.corrector.monitors[-1])
        self.opticsTable.rows = [
            self.corrector._knobs[knob.lower()]
            for elem in elements
            if elem.index < last_mon
            for knob in self.model.get_elem_knobs(elem)
            if knob.lower() in self.corrector._knobs
            and match.search(knob.lower())
        ]

    def _get_filter(self):
        text = self.filterEdit.text()
        text = text.replace(' ', '')
        try:
            return re.compile(text, re.ASCII | re.IGNORECASE)
        except re.error:
            return None

    def change_output_file(self):
        from madgui.widget.filedialog import getSaveFolderName
        folder = getSaveFolderName(
            self.window(), 'Output folder', self.folder)
        if folder:
            self.set_folder(folder)

    def set_folder(self, folder):
        self.folder = os.path.abspath(folder)
        self.folderEdit.setText(self.folder)

    @property
    def running(self):
        return bool(self.bot) and self.bot.running

    def closeEvent(self, event):
        self.bot.cancel()
        super().closeEvent(event)

    def update_ui(self):
        running = self.running
        valid = bool(self.opticsTable.rows and self._get_filter())
        self.cancelButton.setEnabled(running)
        self.startButton.setEnabled(not running and valid)
        self.folderButton.setEnabled(not running)
        self.numIgnoredSpinBox.setEnabled(not running)
        self.numUsedSpinBox.setEnabled(not running)
        self.monitorTable.setEnabled(not running)
        self.opticsTable.setEnabled(not running)
        self.progressBar.setEnabled(running)
        self.progressBar.setRange(0, self.bot.totalops)
        self.progressBar.setValue(self.bot.progress)

    def set_progress(self, progress):
        self.progressBar.setValue(progress)

    def update_fit(self):
        """Called when procedure finishes succesfully."""
        pass

    def start_bot(self):
        self.corrector.set_optics_delta(self.d_phi, self.defaultSpinBox.value())

        now = time.localtime(time.time())
        fname = os.path.join(
            self.folderEdit.text(),
            self.fileEdit.text().format(
                date=time.strftime("%Y-%m-%d", now),
                time=time.strftime("%H-%M-%S", now),
                sequence=self.model.seq_name,
                monitor=self.corrector.monitors[-1],
            ))

        self.corrector.open_export(fname)

        self.bot.start(
            self.numIgnoredSpinBox.value(),
            self.numUsedSpinBox.value())

    def log(self, text, *args, **kwargs):
        formatted = text.format(*args, **kwargs)
        logging.info(formatted)
        self.logEdit.appendPlainText(formatted)
