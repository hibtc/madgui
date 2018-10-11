import os
import time

import textwrap

import madgui.util.yaml as yaml
from madgui.qt import QtCore, QtGui, load_ui
from madgui.widget.tableview import TableItem

from madgui.online.optic_variation import Corrector, ProcBot as _ProcBot


class MeasureWidget(QtGui.QWidget):

    ui_file = 'orm_measure.ui'
    extension = '.orm_measurement.yml'

    def __init__(self, session):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
        self.control = session.control
        self.model = session.model()

        kick_elements = ('hkicker', 'vkicker', 'kicker', 'sbend')
        self.kickers = [elem for elem in self.model.elements
                        if elem.base_name.lower() in kick_elements]
        self.monitors = [elem for elem in self.model.elements
                         if elem.base_name.lower().endswith('monitor')]

        self.config = {
            'monitors': [],
            'steerers': {'x': [], 'y': []},
            'targets':  {},
            'optics':   [],
        }

        self.corrector = Corrector(session, {'default': self.config})
        self.corrector.setup('default')
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

    def set_initial_values(self):
        self.set_folder('.')    # FIXME
        self.ctrl_file.setText(
            "{date}_{time}_{sequence}_{monitor}"+self.extension)
        self.d_phi = {}
        self.default_dphi = 1e-4
        self.ctrl_correctors.rows[:] = []
        self.ctrl_monitors.rows[:] = [elem.name for elem in self.monitors]
        self.update_ui()

    def connect_signals(self):
        self.btn_dir.clicked.connect(self.change_output_file)
        self.btn_start.clicked.connect(self.start)
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
        monitors = sorted({
            self.monitors[idx.row()].index
            for idx in self.ctrl_monitors.selectedIndexes()})
        last_monitor = max(monitors, default=0)

        self.elem_knobs = elem_knobs = [
            (elem, knob) for elem in self.kickers
            if elem.index < last_monitor
            for knob in self.model.get_elem_knobs(elem)
        ]

        self.config.update({
            'monitors': [self.model.elements[idx].name for idx in monitors],
            'steerers': {
                'x': [knob for elem, knob in elem_knobs
                      if elem.base_name != 'vkicker'],
                'y': [knob for elem, knob in elem_knobs
                      if elem.base_name == 'vkicker'],
            },
            'optics': [knob for _, knob in elem_knobs],
        })
        self.corrector.setup(self.corrector.active, force=True)
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

    def start(self):
        self.control.read_all()
        self.corrector.base_optics = {
            par.name.lower(): self.model.read_param(par.name)
            for par in self.control.get_knobs()
        }
        self.corrector.optics = [] + [
            {knob: val + self.d_phi.get(knob.lower(), self.default_dphi)}
            for knob, val in self.corrector._read_vars().items() if val
        ]
        self.bot.start()

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

    def update_fit(self):
        """Called when procedure finishes succesfully."""
        pass

    def add_record(self, step, shot):
        self.corrector.update_readouts()
        records = self.corrector.current_orbit_records()
        if shot == 0:
            self.bot.write_data([{
                'optics': self.corrector.optics[step],
            }])
            self.bot.file.write('  shots:\n')
        self.bot.write_data([{
            r.monitor: [r.readout.posx, r.readout.posy,
                        r.readout.envx, r.readout.envy]
            for r in records
        }], "  ")


class ProcBot(_ProcBot):

    def start(self):
        super().start()
        now = time.localtime(time.time())
        fname = os.path.join(
            self.widget.ctrl_dir.text(),
            self.widget.ctrl_file.text().format(
                date=time.strftime("%Y-%m-%d", now),
                time=time.strftime("%H-%M-%S", now),
                sequence=self.model.seq_name,
                monitor=self.corrector.monitors[-1],
            ))
        self.file = open(fname, 'wt', encoding='utf-8')

        self.write_data({
            'sequence': self.model.seq_name,
            'monitors': self.corrector.selected['monitors'],
            'steerers': [elem.name for elem, _ in self.widget.elem_knobs],
            'knobs':    [knob for _, knob in self.widget.elem_knobs],
            'twiss_args': self.model._get_twiss_args(),
        })
        self.write_data({
            'model': self.corrector.base_optics,
        }, default_flow_style=False)
        self.file.write(
            '#    posx[m]    posy[m]    envx[m]    envy[m]\n'
            'records:\n')

    def stop(self):
        super().stop()
        self.file.close()

    def write_data(self, data, indent="", **kwd):
        self.file.write(textwrap.indent(yaml.safe_dump(data, **kwd), indent))
