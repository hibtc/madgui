import os
from collections import namedtuple

import numpy as np


from madgui.qt import QtCore, QtGui
from madgui.util import yaml
from madgui.util.qt import monospace, load_ui
from madgui.util.collections import List
from madgui.widget.tableview import TableItem


ResultItem = namedtuple('ResultItem', ['name', 'x', 'y'])
Buttons = QtGui.QDialogButtonBox


class OffsetCalibrationWidget(QtGui.QWidget):

    ui_file = 'offcal.ui'
    running = False
    totalops = 100
    progress = 0
    extension = '.calibration.yml'

    def get_result_row(self, i, r) -> ("Monitor", "Δx", "Δy"):
        return [
            TableItem(r.name),
            TableItem(r.x, name='x'),
            TableItem(r.y, name='y'),
        ]

    def __init__(self, parent, monitors):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
        self.ctrl_optics.setFont(monospace())
        self.control = parent.control
        self.model = parent.model
        self.monitors = monitors
        self._parent = parent
        self.fit_results = List()
        last_monitor = max(map(self.model.elements.index, monitors))
        quads = [el.name for el in self.model.elements
                 if el.base_name.lower() == 'quadrupole'
                 and el.index < last_monitor]
        self.quad_knobs = {
            name.lower(): knob
            for name in quads
            for knob in self.model._get_knobs(self.model.elements[name], 'k1')
        }
        self.ctrl_quads.addItems(list(quads))
        self.ctrl_quads.setCurrentItem(
            self.ctrl_quads.item(len(quads)-1),
            QtCore.QItemSelectionModel.SelectCurrent)
        self.ctrl_quads.setCurrentItem(
            self.ctrl_quads.item(len(quads)-2),
            QtCore.QItemSelectionModel.Select)
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
        self.btn_load = self.btns_io.button(Buttons.Open)
        self.btn_save = self.btns_io.button(Buttons.Save)
        self.btn_load.clicked.connect(self.load_optics)
        self.btn_save.clicked.connect(self.save_optics)
        self.btn_focus.clicked.connect(self.read_focus)
        self.ctrl_optics.textChanged.connect(self.update_ui)
        self.ctrl_quads.itemSelectionChanged.connect(self.update_ui)
        self.ctrl_results.set_viewmodel(
            self.get_result_row, self.fit_results, unit=True)
        self.update_filename()
        self.btn_file.clicked.connect(self.change_output_file)
        self.update_ui()

    def _close(self):
        self.window().close()

    def closeEvent(self, event):
        self.cancel()
        super().closeEvent(event)

    def start(self):
        self.selected = self.get_quads()
        self.optics = self.get_optics()

        self.numsteps = len(self.optics)
        self.numshots = self.ctrl_numshots.value()
        self.totalops = self.numsteps * self.numshots
        self.control.read_all()
        self.base_optics = {knob: self.model.read_param(knob)
                            for knob in self.control.get_knobs()}
        self.progress = -1
        self.backup = {p: self.base_optics[p.lower()]
                       for q in self.selected
                       for p in [self.quad_knobs[q]]}
        self.sectormaps = None
        self.output_file = open(self.filename, 'wt')
        yaml.safe_dump({
            'monitors': self.monitors,
            'selected': self.selected,
            'optics': self.optics,
            'base_optics': self.base_optics,
            'numsteps': self.numsteps,
            'numshots': self.numshots,
        }, self.output_file, default_flow_style=False)
        self.output_file.write('records:\n')
        self.readouts = []
        self.running = True
        self.ctrl_tab.setCurrentIndex(1)
        self.control.sampler.updated.connect(self._feed)
        self._advance()
        self.update_ui()

    def cancel(self):
        self.stop()
        self.reset()

    def stop(self):
        if self.running:
            self.running = False
            self.output_file.close()
            self.control.sampler.updated.disconnect(self._feed)
            self.restore()
            self.update_ui()

    filename_filters = [
        ("YAML files", "*.yml", "*.yaml"),
        ("All files", "*"),
    ]

    def load_optics(self):
        from madgui.widget.filedialog import getOpenFileName
        filename = getOpenFileName(
            self, 'Open file', self.folder, self.filename_filters)
        if filename:
            with open(filename) as f:
                self.ctrl_optics.setPlainText(f.read())

    def save_optics(self):
        from madgui.widget.filedialog import getSaveFileName
        filename = getSaveFileName(
            self, 'Open file', self.folder, self.filename_filters)
        if filename:
            with open(filename, 'wt') as f:
                f.write(self.ctrl_optics.toPlainText())

    def read_focus(self):
        focus_levels = parse_ints(self.ctrl_focus.text())

        # TODO: this should be done with a more generic API
        # TODO: do this without beamoptikdll to decrease the waiting time
        plug = self.control.backend
        dll = self.control.backend.beamoptikdll
        values, channels = dll.GetMEFIValue()
        vacc = dll.GetSelectedVAcc()

        knobs = {self.quad_knobs[q] for q in self.get_quads()}

        optics = []
        for focus in focus_levels:
            dll.SelectMEFI(vacc, *channels._replace(focus=focus))
            optics.append({
                k: plug.read_param(k)
                for k in knobs
            })

        dll.SelectMEFI(vacc, *channels)

        self.ctrl_optics.setPlainText(yaml.safe_dump(
            optics, default_flow_style=False))

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
        valid_optics = self.is_optics_valid()
        self.btn_start.setEnabled(not running and len(self.fit_results) == 0
                                  and valid_optics)
        self.btn_close.setEnabled(not running)
        self.btn_abort.setEnabled(running)
        self.btn_reset.setEnabled(not running and len(self.fit_results) > 0)
        self.btn_apply.setEnabled(not running and len(self.fit_results) > 0)
        self.btn_focus.setEnabled(not running)
        self.btn_load.setEnabled(not running)
        self.btn_save.setEnabled(not running)
        self.ctrl_quads.setEnabled(not running)
        self.ctrl_optics.setReadOnly(running)
        self.ctrl_focus.setReadOnly(running)
        self.ctrl_numshots.setReadOnly(running)
        self.ctrl_progress.setRange(0, self.totalops)
        self.ctrl_progress.setValue(self.progress)

    def restore(self):
        if self.backup:
            self.control.write_params(self.backup.items())
            self.model.write_params(self.backup.items())
            self.backup = None

    def get_quads(self):
        return [item.text() for item in self.ctrl_quads.selectedItems()]

    def get_optics(self):
        parsed = yaml.safe_load(self.ctrl_optics.toPlainText())
        if not isinstance(parsed, list):
            raise TypeError
        if any(not isinstance(item, dict) for item in parsed):
            raise TypeError
        quads = self.get_quads()
        knobs = {self.quad_knobs[q].lower() for q in quads}
        filtered = [
            {k: v for k, v in optic.items() if k.lower() in knobs}
            for optic in parsed
        ]
        return [optic for optic in filtered if optic]

    def is_optics_valid(self):
        try:
            optics = self.get_optics()
        except (ValueError, TypeError, yaml.YAMLError):
            return False
        return len(optics) > 0

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

    def _feed(self, time, activity):
        progress = self.progress
        step = progress // self.numshots % self.numsteps
        shot = progress % self.numshots

        readouts = self.control.sampler.readouts

        self.log('  -> shot {}', shot+1)
        yaml.safe_dump([{
            'step': step,
            'shot': shot,
            'optics': self.optics[step],
            'time': time,
            'active': list(activity),
            'readout': readouts,
        }], self.output_file, default_flow_style=False)

        self.shots.append([
            (readouts[mon]['posx'], readouts[mon]['posy'])
            for mon in self.monitors
        ])

        if len(self.readouts) >= 3:
            self.update_results()

        self._advance()

    def _advance(self):
        progress = self.progress = self.progress + 1
        print(progress, self.totalops)
        step = progress // self.numshots % self.numsteps
        shot = progress % self.numshots
        self.ctrl_progress.setValue(progress)

        if progress == self.totalops:
            self.finish()

        elif shot == 0:
            quad = min(map(self.model.elements.index, self.selected))
            kL = self.optics[step]

            self.log(" " + ", ".join(
                '{}={:.4f}'.format(k, v) for k, v in kL.items()))

            self.control.write_params(kL.items())
            self.model.write_params(kL.items())

            # TODO: don't need to redo the "zero-step"-shot for every quad
            # change optics before first shot
            sectormaps = [self.model.sectormap(quad-1, mon)
                          for mon in self.monitors]
            self.shots = []
            self.readouts.append((sectormaps, self.shots))

    def finish(self):
        self.stop()
        self.log("Finished\n")
        self.ctrl_tab.setCurrentIndex(2)

    def round(self, value):
        return round(value*10000)/10000

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

            records = [(m[0:6, 0:6], m[0:6, 6], r)
                       for m, r in zip(maps, read)]

            x0, res, sing = fit_monitor_offsets(*records)
            offsets = -x0[-2:]

            fit_results.append(ResultItem(mon, *offsets))

        self.fit_results[:] = fit_results

    def log(self, text, *args, **kwargs):
        self.ctrl_log.appendPlainText(text.format(*args, **kwargs))


def parse_ints(text):
    try:
        return [int(x) for x in text.split(',') if x.strip()]
    except ValueError:
        return []


def _fit_monitor_offsets(*records):
    T_, K_, Y_ = zip(*records)
    E = np.eye(2)
    B = lambda t: np.hstack((t[:, :4], E))
    T = np.vstack([B(T[[0, 2]]) for T in T_])
    K = np.hstack([K[[0, 2]] for K in K_])
    Y = np.hstack(Y_)
    T, K, Y = 1000*T, 1000*K, 1000*Y
    x, residuals, rank, singular = np.linalg.lstsq(T, Y-K, rcond=1e-7)
    x /= 1000
    return x, sum(residuals), (rank < len(x))


def fit_monitor_offsets(*records):
    T_, K_, Y_ = zip(*records)

    T0, K0, Y0 = T_[0], K_[0], Y_[0]
    T_ = np.array([t-T0 for t in T_[1:]])
    K_ = np.array([k-K0 for k in K_[1:]])
    Y_ = np.array([y-Y0 for y in Y_[1:]])

    T = np.vstack([T[[0, 2]] for T in T_])[:, :4]
    K = np.hstack([K[[0, 2]] for K in K_])
    Y = np.hstack(Y_)

    T, K, Y = 1000*T, 1000*K, 1000*Y
    x, residuals, rank, singular = np.linalg.lstsq(T, Y-K, rcond=-1)
    x /= 1000

    T0 = T0[[0, 2]][:, :4]
    K0 = K0[[0, 2]]
    o = Y0 - (np.dot(T0, x) + K0)

    return np.hstack((x, o)), sum(residuals), (rank < len(x))
