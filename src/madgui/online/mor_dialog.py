"""
Multi grid correction method.
"""

from collections import namedtuple
from functools import partial
import os
import time

import numpy as np
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QAbstractItemView, QMessageBox, QWidget

from madgui.util.unit import change_unit, get_raw_label
from madgui.util.collections import List
from madgui.util.history import History
from madgui.util.qt import bold, Queued, load_ui
from madgui.util import yaml
from madgui.widget.dialog import Dialog
from madgui.widget.tableview import TableItem, delegates
from madgui.widget.edit import TextEditDialog

from .procedure import Corrector, Target, ProcBot


ORM_Entry = namedtuple('ORM_Entry', ['monitor', 'knob', 'x', 'y'])


class CorrectorWidget(QWidget):

    ui_file = 'mor_dialog.ui'
    data_key = 'multi_grid'     # can reuse the multi grid configuration

    def get_orm_row(self, i, r) -> (
            "Steerer", "Monitor", "X [mm/mrad]", "Y [mm/mrad]"):
        return [
            TableItem(r.knob),
            TableItem(r.monitor),
            TableItem(r.x),     # TODO: set_value and delegate
            TableItem(r.y),
        ]

    def get_readout_row(self, i, r) -> ("Monitor", "X", "Y"):
        return [
            TableItem(r.name),
            TableItem(r.posx, name='posx'),
            TableItem(r.posy, name='posy'),
        ]

    def get_cons_row(self, i, t) -> ("Target", "X", "Y"):
        mode = self.corrector.mode
        active_x = 'x' in mode
        active_y = 'y' in mode
        textcolor = QColor(Qt.darkGray), QColor(Qt.black)
        return [
            TableItem(t.elem),
            TableItem(t.x, name='x', set_value=self.set_x_value,
                      editable=active_x, foreground=textcolor[active_x],
                      delegate=delegates[float]),
            TableItem(t.y, name='y', set_value=self.set_y_value,
                      editable=active_y, foreground=textcolor[active_y],
                      delegate=delegates[float]),
        ]

    def get_steerer_row(self, i, v) -> ("Steerer", "Now", "To Be", "Unit"):
        initial = self.corrector.online_optic.get(v.lower())
        matched = self.corrector.saved_optics().get(v.lower())
        changed = matched is not None and not np.isclose(initial, matched)
        style = {
            # 'foreground': QColor(Qt.red),
            'font': bold(),
        } if changed else {}
        info = self.corrector._knobs[v.lower()]
        return [
            TableItem(v),
            TableItem(change_unit(initial, info.unit, info.ui_unit)),
            TableItem(change_unit(matched, info.unit, info.ui_unit),
                      set_value=self.set_steerer_value,
                      delegate=delegates[float], **style),
            TableItem(get_raw_label(info.ui_unit)),
        ]

    def set_x_value(self, i, t, value):
        self.corrector.targets[i] = Target(t.elem, value, t.y)

    def set_y_value(self, i, t, value):
        self.corrector.targets[i] = Target(t.elem, t.x, value)

    def set_steerer_value(self, i, v, value):
        info = self.corrector._knobs[v.lower()]
        value = change_unit(value, info.ui_unit, info.unit)
        results = self.corrector.saved_optics().copy()
        if results[v.lower()] != value:
            results[v.lower()] = value
            self.corrector._push_history(results)
            self.update_ui()

    def __init__(self, session, active=None):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
        self.orm = List()
        self.saved_orms = History()
        self.configs = session.model().data.get(self.data_key, {})
        self.active = active or next(iter(self.configs))
        self.corrector = Corrector(session)
        self.corrector.start()
        self.corrector.setup(self.configs[self.active])
        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    def closeEvent(self, event):
        self.corrector.stop()
        self.view.del_curve("readouts")

    def on_execute_corrections(self):
        """Apply calculated corrections."""
        self.corrector.apply()
        self.update_status()

    def init_controls(self):
        for tab in (self.monitorTable, self.targetsTable, self.resultsTable):
            tab.setSelectionBehavior(QAbstractItemView.SelectRows)
            tab.setSelectionMode(QAbstractItemView.ExtendedSelection)
        corr = self.corrector
        self.ormTable.set_viewmodel(
            self.get_orm_row, self.orm)
        self.monitorTable.set_viewmodel(
            self.get_readout_row, corr.readouts, unit=True)
        self.resultsTable.set_viewmodel(
            self.get_steerer_row, corr.variables)
        self.targetsTable.set_viewmodel(
            self.get_cons_row, corr.targets, unit=True)
        self.view = self.corrector.session.window().open_graph('orbit')

    def set_orm(self, orm):
        self.hist_index += 1
        self.hist_stack[self.hist_index:] = [orm]
        self.orm[:] = orm
        self.update_ui()

    def prev_orm(self):
        if self.saved_orms.undo():
            self.orm[:] = self.saved_orms()
            self.update_ui()

    def next_orm(self):
        if self.saved_orms.redo():
            self.orm[:] = self.saved_orms()
            self.update_ui()

    def set_initial_values(self):
        self.fitButton.setFocus()
        self.modeXYButton.setChecked(True)
        self.update_config()
        self.update_status()

    def update_config(self):
        self.configComboBox.clear()
        self.configComboBox.addItems(list(self.configs))
        self.configComboBox.setCurrentText(self.active)

    def connect_signals(self):
        self.computeButton.clicked.connect(self.compute_orm)
        self.measureButton.clicked.connect(self.measure_orm)
        self.loadButton.clicked.connect(self.load_orm)
        self.saveButton.clicked.connect(self.save_orm)
        self.fitButton.clicked.connect(self.update_fit)
        self.applyButton.clicked.connect(self.on_execute_corrections)
        self.configComboBox.activated.connect(self.on_change_config)
        self.editConfigButton.clicked.connect(self.edit_config)
        self.modeXButton.clicked.connect(partial(self.on_change_mode, 'x'))
        self.modeYButton.clicked.connect(partial(self.on_change_mode, 'y'))
        self.modeXYButton.clicked.connect(partial(self.on_change_mode, 'xy'))
        self.prevButton.clicked.connect(self.prev_vals)
        self.nextButton.clicked.connect(self.next_vals)
        self.prevORMButton.clicked.connect(self.prev_orm)
        self.nextORMButton.clicked.connect(self.next_orm)

    def update_status(self):
        self.corrector.update_vars()
        self.update_ui()

    def measure_orm(self):
        widget = MeasureWidget(self.corrector)
        dialog = Dialog(self.window())
        dialog.setWidget(widget)
        dialog.setWindowTitle("ORM scan")
        if dialog.exec_():
            self.set_orm(widget.final_orm)

    def compute_orm(self):
        # TODO: for generic knobs (anything other than hkicker/vkicker->kick)
        # we need to use numerical ORM
        corrector = self.corrector
        sectormap = corrector.compute_sectormap().reshape((
            len(corrector.monitors), 2, len(corrector.variables)))
        self.set_orm([
            ORM_Entry(mon, var, *sectormap[i_mon, :, i_var])
            for i_var, var in enumerate(corrector.variables)
            for i_mon, mon in enumerate(corrector.monitors)
        ])

    folder = '.'
    exportFilters = [
        ("YAML file", "*.yml"),
    ]

    def load_orm(self):
        from madgui.widget.filedialog import getOpenFileName
        filename = getOpenFileName(
            self.window(), 'Load Orbit Responses', self.folder,
            self.exportFilters)
        if filename:
            self.load_from(filename)

    def save_orm(self):
        from madgui.widget.filedialog import getSaveFileName
        filename = getSaveFileName(
            self.window(), 'Export Orbit Responses', self.folder,
            self.exportFilters)
        if filename:
            self.export_to(filename)
            self.folder, _ = os.path.split(filename)

    def load_from(self, filename):
        data = yaml.load_file(filename)['orm']
        self.set_orm([
            ORM_Entry(*entry)
            for entry in data
        ])

    def export_to(self, filename):
        yaml.save_file(filename, {
            'orm': [
                [entry.monitor, entry.knob, entry.x, entry.y]
                for entry in self.orm
            ]
        }, default_flow_style=True)

    def update_fit(self):
        """Calculate initial positions / corrections."""
        indexed = {}
        for entry in self.orm:
            monitor = entry.monitor.lower()
            knob = entry.knob.lower()
            indexed.setdefault(monitor, {})[knob] = [entry.x, entry.y]

        orm = np.array([
            [
                indexed[mon.lower()][var.lower()]
                for var in self.corrector.variables
            ]
            for mon in self.corrector.monitors
        ])
        orm = orm.transpose((0, 2, 1)).reshape(
            (2*len(self.corrector.monitors), len(self.corrector.variables)))
        results = self.corrector._compute_steerer_corrections_orm(orm)

        self.corrector.saved_optics.push(results)
        self.update_ui()

    def on_change_config(self, index):
        name = self.configComboBox.itemText(index)
        self.corrector.setup(self.configs[name], self.corrector.mode)
        self.update_status()

    def on_change_mode(self, dirs):
        self.corrector.setup(self.configs[self.active], dirs)
        self.update_status()

        # TODO: make 'optimal'-column in resultsTable editable and update
        #       self.applyButton.setEnabled according to its values

    def prev_vals(self):
        self.corrector.saved_optics.undo()
        self.update_ui()

    def next_vals(self):
        self.corrector.saved_optics.redo()
        self.update_ui()

    def update_ui(self):
        saved_optics = self.corrector.saved_optics
        self.prevButton.setEnabled(saved_optics.can_undo())
        self.nextButton.setEnabled(saved_optics.can_redo())
        self.applyButton.setEnabled(
            self.corrector.online_optic != saved_optics())
        self.corrector.variables.touch()
        self.prevORMButton.setEnabled(self.saved_orms.can_undo())
        self.nextORMButton.setEnabled(self.saved_orms.can_redo())
        self.draw_idle()

    def edit_config(self):
        model = self.corrector.model
        with open(model.filename) as f:
            text = f.read()
        dialog = TextEditDialog(text, self.apply_config)
        dialog.setWindowTitle(model.filename)
        dialog.exec_()

    def apply_config(self, text):
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            QMessageBox.critical(
                self,
                'Syntax error in YAML document',
                'There is a syntax error in the YAML document, please edit.')
            return False

        configs = data.get(self.data_key)
        if not configs:
            QMessageBox.critical(
                self,
                'No config defined',
                'No configuration for this method defined.')
            return False

        model = self.corrector.model
        with open(model.filename, 'w') as f:
            f.write(text)

        self.configs = configs
        model.data[self.data_key] = configs
        conf = self.active
        if conf not in configs:
            conf = next(iter(configs))

        self.corrector.setup(conf)
        self.update_config()
        self.update_status()

        return True

    @Queued.method
    def draw_idle(self):
        self.view.show_monitor_readouts(self.corrector.monitors[:])

    @property
    def frame(self):
        return self.corrector.session.window()


class MeasureWidget(QWidget):

    ui_file = 'mor_measure.ui'
    extension = '.orm_measurement.yml'

    def __init__(self, corrector):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
        self.corrector = Corrector(corrector.session, False)
        self.corrector.setup({
            'monitors': corrector.monitors,
            'optics': corrector.variables,
        })
        self.corrector.start()
        self.bot = ProcBot(self, self.corrector)

        elem_by_knob = {}
        for elem in corrector.model.elements:
            for knob in corrector.model.get_elem_knobs(elem):
                elem_by_knob.setdefault(knob.lower(), elem)

        self.steerers = [
            elem_by_knob[v.lower()]
            for v in corrector.variables
        ]

        self.corrector.add_record = self.add_record
        self.raw_records = []

        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    def add_record(self, step, shot):
        if shot == 0:
            self.raw_records.append([])
        records = {r.name: r.data for r in self.corrector.readouts}
        self.raw_records[-1].append(records)
        self.corrector.write_shot(step, shot, {
            monitor: [data['posx'], data['posy'],
                      data['envx'], data['envy']]
            for monitor, data in records.items()
        })

    def sizeHint(self):
        return QSize(600, 400)

    def init_controls(self):
        self.opticsTable.set_viewmodel(
            self.get_corrector_row, unit=(None, 'kick'))

    def set_initial_values(self):
        self.d_phi = {}
        self.default_dphi = 2e-4
        self.opticsTable.rows[:] = self.steerers
        self.fileEdit.setText(
            "{date}_{time}_{sequence}_{monitor}"+self.extension)
        self.update_ui()

    def connect_signals(self):
        self.startButton.clicked.connect(self.start_bot)
        self.cancelButton.clicked.connect(self.cancel)

    def get_corrector_row(self, i, c) -> ("Kicker", "ΔΦ"):
        return [
            TableItem(c.name),
            TableItem(self.d_phi.get(c.name.lower(), self.default_dphi),
                      name='kick', set_value=self.set_kick,
                      delegate=delegates[float]),
        ]

    def set_kick(self, i, c, value):
        self.d_phi[c.name.lower()] = value

    @property
    def running(self):
        return bool(self.bot) and self.bot.running

    def closeEvent(self, event):
        self.bot.cancel()
        super().closeEvent(event)

    def update_ui(self):
        running = self.running
        valid = bool(self.corrector.optic_params)
        self.cancelButton.setEnabled(running)
        self.startButton.setEnabled(not running and valid)
        self.numIgnoredSpinBox.setEnabled(not running)
        self.numUsedSpinBox.setEnabled(not running)
        self.opticsTable.setEnabled(not running)
        self.progressBar.setEnabled(running)
        self.progressBar.setRange(0, self.bot.totalops)
        self.progressBar.setValue(self.bot.progress)

    def set_progress(self, progress):
        self.progressBar.setValue(progress)

    def update_fit(self):
        """Called when procedure finishes succesfully."""
        full_data = np.array([
            [
                np.mean([
                    [shot[monitor]['posx'], shot[monitor]['posy']]
                    for shot in series
                ], axis=0)
                for monitor in self.corrector.monitors
            ]
            for series in self.raw_records
        ])
        differences = full_data[1:] - full_data[[0]]
        deltas = [
            self.d_phi.get(v.lower(), self.default_dphi)
            for v in self.corrector.variables
        ]
        self.final_orm = [
            ORM_Entry(mon, var, *differences[i_var, i_mon] / deltas[i_var])
            for i_var, var in enumerate(self.corrector.variables)
            for i_mon, mon in enumerate(self.corrector.monitors)
        ]

        self.window().accept()

    def start_bot(self):
        self.corrector.set_optics_delta(self.d_phi, self.default_dphi)
        self.bot.start(
            self.numIgnoredSpinBox.value(),
            self.numUsedSpinBox.value())

        now = time.localtime(time.time())
        fname = os.path.join(
            '.',
            self.fileEdit.text().format(
                date=time.strftime("%Y-%m-%d", now),
                time=time.strftime("%H-%M-%S", now),
                sequence=self.corrector.model.seq_name,
                monitor=self.corrector.monitors[-1],
            ))

        self.corrector.open_export(fname)

    def cancel(self):
        self.bot.cancel()
        self.window().reject()

    def log(self, text, *args, **kwargs):
        formatted = text.format(*args, **kwargs)
        self.logEdit.appendPlainText(formatted)
