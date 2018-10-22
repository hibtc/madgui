import os
import time
import logging

from madgui.qt import QtCore, QtGui, load_ui
from madgui.widget.tableview import TableItem

from madgui.online.procedure import Corrector, ProcBot


class MeasureWidget(QtGui.QWidget):

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
        return QtCore.QSize(600, 400)

    def init_controls(self):
        self.ctrl_correctors.set_viewmodel(
            self.get_corrector_row, unit=(None, 'kick'))
        self.ctrl_monitors.set_viewmodel(self.get_monitor_row)
        self.corrector.session.window().open_graph('orbit')

    def set_initial_values(self):
        self.set_folder('.')    # FIXME
        self.ctrl_file.setText(
            "{date}_{time}_{sequence}_{monitor}"+self.extension)
        self.d_phi = {}
        self.default_dphi = 2e-4
        self.ctrl_correctors.rows[:] = []
        self.ctrl_monitors.rows[:] = self.corrector.all_monitors
        self.update_ui()

    def connect_signals(self):
        self.btn_dir.clicked.connect(self.change_output_file)
        self.btn_start.clicked.connect(self.start_bot)
        self.btn_cancel.clicked.connect(self.bot.cancel)
        self.ctrl_monitors.selectionModel().selectionChanged.connect(
            self.monitor_selection_changed)

    def get_monitor_row(self, i, m) -> ("Monitor",):
        return [
            TableItem(m),
        ]

    def get_corrector_row(self, i, c) -> ("Kicker", "ΔΦ"):
        return [
            TableItem(c.name),
            TableItem(self.d_phi.get(c.name.lower(), self.default_dphi),
                      name='kick', set_value=self.set_kick),
        ]

    def set_kick(self, i, c, value):
        self.d_phi[c.name.lower()] = value

    def monitor_selection_changed(self, selected, deselected):
        self.corrector.setup({
            'monitors': [
                self.corrector.all_monitors[idx.row()]
                for idx in self.ctrl_monitors.selectedIndexes()
            ],
        })
        self.ctrl_correctors.rows = self.corrector.optic_params
        self.update_ui()

    def change_output_file(self):
        from madgui.widget.filedialog import getSaveFolderName
        folder = getSaveFolderName(
            self.window(), 'Output folder', self.folder)
        if folder:
            self.set_folder(folder)

    def set_folder(self, folder):
        self.folder = os.path.abspath(folder)
        self.ctrl_dir.setText(self.folder)

    @property
    def running(self):
        return bool(self.bot) and self.bot.running

    def closeEvent(self, event):
        self.bot.cancel()
        super().closeEvent(event)

    def update_ui(self):
        running = self.running
        valid = bool(self.corrector.optic_params)
        self.btn_cancel.setEnabled(running)
        self.btn_start.setEnabled(not running and valid)
        self.btn_dir.setEnabled(not running)
        self.num_shots_wait.setEnabled(not running)
        self.num_shots_use.setEnabled(not running)
        self.ctrl_monitors.setEnabled(not running)
        self.ctrl_correctors.setEnabled(not running)
        self.ctrl_progress.setEnabled(running)
        self.ctrl_progress.setRange(0, self.bot.totalops)
        self.ctrl_progress.setValue(self.bot.progress)

    def set_progress(self, progress):
        self.ctrl_progress.setValue(progress)

    def update_fit(self):
        """Called when procedure finishes succesfully."""
        pass

    def start_bot(self):
        self.control.read_all()
        self.corrector.set_optics_delta(self.d_phi, self.default_dphi)

        self.bot.start(
            self.num_shots_wait.value(),
            self.num_shots_use.value())

        now = time.localtime(time.time())
        fname = os.path.join(
            self.ctrl_dir.text(),
            self.ctrl_file.text().format(
                date=time.strftime("%Y-%m-%d", now),
                time=time.strftime("%H-%M-%S", now),
                sequence=self.model.seq_name,
                monitor=self.corrector.monitors[-1],
            ))

        self.corrector.open_export(fname)

    def log(self, text, *args, **kwargs):
        formatted = text.format(*args, **kwargs)
        logging.info(formatted)
        self.status_log.appendPlainText(formatted)
