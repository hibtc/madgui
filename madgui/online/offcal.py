import os
from collections import namedtuple

import numpy as np


from madgui.qt import QtCore, QtGui, load_ui
from madgui.util import yaml
from madgui.util.collections import List
from madgui.widget.tableview import ColumnInfo


ResultItem = namedtuple('ResultItem', ['name', 'x', 'y'])
Buttons = QtGui.QDialogButtonBox


class OffsetCalibrationWidget(QtGui.QWidget):

    ui_file = 'offcal.ui'
    running = False
    totalops = 100
    progress = 0
    extension = '.calibration.yml'

    result_columns = [
        ColumnInfo('Monitor', 'name'),
        ColumnInfo('Δx', 'x', convert=True),
        ColumnInfo('Δy', 'y', convert=True),
    ]

    def __init__(self, parent, monitors):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
        self.control = parent.control
        self.model = parent.model
        self.monitors = monitors
        self._parent = parent
        self.fit_results = List()
        first_monitor = min(map(self.model.elements.index, monitors))
        quads = [el.name for el in self.model.elements
                 if el.base_name.lower() == 'quadrupole'
                 and el.index < first_monitor]
        self.ctrl_quads.addItems(list(quads))
        self.ctrl_quads.setCurrentItem(
            self.ctrl_quads.item(len(quads)-1),
            QtCore.QItemSelectionModel.SelectCurrent)
        self.btn_start = self.btns.button(Buttons.Ok)
        self.btn_abort = self.btns.button(Buttons.Abort)
        self.btn_close = self.btns.button(Buttons.Close)
        self.btn_reset = self.btns.button(Buttons.Reset)
        self.btn_apply = self.btns.button(Buttons.Apply)
        self.btn_start.clicked.connect(self.start)
        self.btn_abort.clicked.connect(self.cancel)
        self.btn_close.clicked.connect(self._close)
        self.btn_reset.clicked.connect(self.reset)
        self.btn_apply.clicked.connect(self.apply)
        self.ctrl_results.set_columns(self.result_columns, self.fit_results)
        self.update_filename()
        self.btn_file.clicked.connect(self.change_output_file)
        self.update_ui()

    def _close(self):
        self.window().close()

    def closeEvent(self, event):
        self.cancel()
        super().closeEvent(event)

    def start(self):
        self.selected = [item.text() for item in self.ctrl_quads.selectedItems()]
        self.stepsize = self.ctrl_stepsize.value()
        self.numsteps = self.ctrl_numsteps.value()
        self.numshots = self.ctrl_numshots.value()
        self.relative = self.radio_active.isChecked()
        self.totalops = len(self.selected) * self.numsteps * self.numshots
        self.prepare = True
        self.control.read_all()
        self.base_optics = {par.name.lower(): self.model.read_param(par.name)
                            for par in self.control.get_knobs()}
        self.quad_knobs = {
            name: knob
            for name in self.selected
            for knob in self.model._get_knobs(self.model.elements[name], 'k1')
        }
        self.progress = 0
        self.backup = None
        self.sectormaps = None
        self.output_file = open(self.filename, 'wt')
        yaml.safe_dump({
            'monitors': self.monitors,
            'selected': self.selected,
            'base_optics': self.base_optics,
            'stepsize': self.stepsize,
            'numsteps': self.numsteps,
            'numshots': self.numshots,
            'relative': self.relative,
        }, self.output_file, default_flow_style=False)
        self.output_file.write('records:\n')
        self.readouts = []
        self.running = True
        self.update_ui()
        self.ctrl_tab.setCurrentIndex(1)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.poll)
        self.timer.start(300)

    def cancel(self):
        self.stop()
        self.reset()

    def stop(self):
        if self.running:
            self.running = False
            self.output_file.close()
            self.timer.stop()
            self.restore()
            self.update_ui()

    def update_filename(self):
        folder = self.folder or os.getcwd()
        template = os.path.join(folder, "{}_{}.calibration.yml")
        monitors = "_".join(self.monitors)
        filename = template.format(monitors, 0)
        i = 0
        while os.path.exists(filename):
            i += 1
            filename = template.format(monitors, i)
        self.set_filename(filename)

    def set_filename(self, filename):
        filename = os.path.abspath(filename)
        self.folder, basename = os.path.split(filename)
        self.ctrl_file.setText(basename)
        self.filename = filename

    def update_ui(self):
        running = self.running
        self.btn_start.setEnabled(not running and len(self.fit_results) == 0)
        self.btn_close.setEnabled(not running)
        self.btn_abort.setEnabled(running)
        self.btn_reset.setEnabled(not running and len(self.fit_results) > 0)
        self.btn_apply.setEnabled(not running and len(self.fit_results) > 0)
        self.ctrl_quads.setEnabled(not running)
        self.ctrl_stepsize.setReadOnly(running)
        self.ctrl_numsteps.setReadOnly(running)
        self.ctrl_numshots.setReadOnly(running)
        self.radio_active.setEnabled(not running)
        self.radio_zero.setEnabled(not running)
        self.ctrl_progress.setRange(0, self.totalops)
        self.ctrl_progress.setValue(self.progress)

    def restore(self):
        if self.backup:
            self.control.write_params([self.backup])
            self.model.write_param(*self.backup)
            self.backup = None

    folder = None

    def change_output_file(self):
        if self.running:
            return
        from madgui.widget.filedialog import getSaveFileName
        filename = getSaveFileName(
            self.window(), 'Raw data file', self.folder,
            [("YAML file", "*"+self.extension)])
        if filename:
            if not filename.endswith(self.extension):
                filename += self.extension
            self.set_filename(filename)

    def poll(self):
        if not self.running:
            return

        progress = self.progress
        quad = self.selected[progress // (self.numsteps * self.numshots)]
        step = progress // self.numshots % self.numsteps
        shot = progress % self.numshots
        knob = self.quad_knobs[quad]

        multiplier = ((step+1)//2) * ((-1,+1)[step%2])
        k1 = (multiplier * self.stepsize +
              self.relative * self.base_optics[knob])

        if self.prepare:
            # backup optics
            if step == 0 and shot == 0:
                self.log("quad: {}", quad)
                self.backup = (knob, self.base_optics[knob])

            if shot == 0:
                self.log(" k1 = {}", k1)

            if shot == 0 and (step != 0 or not self.relative):
                self.control.write_params([(knob, k1)])
                self.model.write_param(knob, k1)

            # TODO: don't need to redo the "zero-step"-shot for every quad
            # change optics before first shot

            self.prepare = False
            if shot == 0:
                sectormaps = [self.model.sectormap(quad, mon)
                              for mon in self.monitors]
                self.shots = []
                self.readouts.append((sectormaps, self.shots))
                # after changing optics, always wait for at least one cycle
                self.last_readouts = self.read_monitors()
                return

        readouts = self.read_monitors()
        if readouts == self.last_readouts:
            return

        self.log('  -> shot {}', shot+1)
        yaml.safe_dump([{
            'step': step,
            'shot': shot,
            'optics': {quad: k1},
            'readout': readouts,
        }], self.output_file, default_flow_style=False)

        data = [
            (readouts[mon]['posx'], readouts[mon]['posy'])
            for mon in self.monitors
        ]
        self.shots.append(data)
        self.progress += 1
        self.prepare = True
        self.ctrl_progress.setValue(self.progress)

        if len(self.readouts) > 3:
            self.update_results()

        if shot == self.numshots-1 and step == self.numsteps-1:
            self.restore()
        if self.progress == self.totalops:
            self.finish()

    def finish(self):
        self.stop()
        self.ctrl_tab.setCurrentIndex(2)

    def read_monitors(self):
        return {mon: self.control.read_monitor(mon)
                for mon in self.monitors}

    def reset(self):
        self.fit_results[:] = []
        self.update_filename()
        self.ctrl_tab.setCurrentIndex(0)
        self.update_ui()

    def apply(self):
        self._parent._offsets.update({
            m.name: (m.x, m.y)
            for m in self.fit_results
        })
        self._parent.update()
        self.btn_apply.setEnabled(False)

    def update_results(self):

        fit_results = []

        for i, mon in enumerate(self.monitors):
            maps = np.array([m[i]
                             for m, r in self.readouts])
            read = np.array([np.mean([s[i] for s in r], axis=0)
                             for m, r in self.readouts])

            records = [(m[0:6,0:6], m[0:6,6], r)
                       for m, r in zip(maps, read)]

            x0, res, sing = fit_monitor_offsets(*records)
            offsets = x0[-2:]

            fit_results.append(ResultItem(mon, *offsets))

        self.fit_results[:] = fit_results

    def log(self, text, *args, **kwargs):
        self.ctrl_log.appendPlainText(text.format(*args, **kwargs))


def fit_monitor_offsets(*records):
    T_, K_, Y_ = zip(*records)
    E = np.eye(2)
    B = lambda t: np.hstack((t[:,:4], E))
    T = np.vstack([B(T[[0,2]]) for T in T_])
    K = np.hstack([K[[0,2]] for K in K_])
    Y = np.hstack(Y_)
    x, residuals, rank, singular = np.linalg.lstsq(T, Y-K, rcond=-1)
    return x, sum(residuals), (rank<len(x))
