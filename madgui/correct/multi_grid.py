"""
Multi grid correction method.
"""

# TODO:
# - use CORRECT command from MAD-X rather than custom numpy method?
# - combine with optic variation method

from pkg_resources import resource_filename
from functools import partial
import itertools

import numpy as np
import yaml

from madgui.qt import QtCore, QtGui, uic

from madgui.core.unit import tounit
from madgui.util.collections import List
from madgui.util.layout import VBoxLayout
from madgui.util.qt import fit_button
from madgui.util.font import monospace
from madgui.widget.tableview import ColumnInfo, ExtColumnInfo
from madgui.correct.orbit import fit_initial_orbit

from .match import Matcher, Constraint, variable_from_knob, variable_update


class MonitorReadout:

    def __init__(self, monitor, orbit):
        self.monitor = monitor
        self.x = orbit['posx']
        self.y = orbit['posy']


class Corrector(Matcher):

    """
    Single target orbit correction via optic variation.
    """

    mode = 'xy'

    def __init__(self, control, configs):
        super().__init__(control._model, None)
        self.control = control
        self.configs = configs
        self.control.read_all()
        self.utool = control._model.utool
        knobs = control.get_knobs()
        self._optics = {mknob.param: (mknob, dknob) for mknob, dknob in knobs}
        self._knobs = {mknob.el_name: (mknob, dknob) for mknob, dknob in knobs}
        # save elements
        self.design_values = {}
        self.monitors = List()
        self.readouts = List()
        self.fit_results = List()
        control._frame.open_graph('orbit')

    def setup(self, name, dirs=None):
        dirs = dirs or self.mode

        selected = self.selected = self.configs[name]
        monitors = selected['monitors']
        steerers = sum([selected['steerers'][d] for d in dirs], [])
        targets  = selected['targets']

        self.active = name
        self.mode = dirs

        self.monitors[:] = monitors
        elements = self.model.elements
        self.constraints[:] = sorted([
            Constraint(elements[target], elements[target].At, key,
                       self.utool.add_unit(key, value))
            for target, values in targets.items()
            for key, value in values.items()
            if key[-1] in dirs
        ], key=lambda c: c.pos)
        self.variables[:] = sorted([
            variable_from_knob(self, self._knobs[el.lower()][0])
            for el in steerers
        ], key=lambda v: v.pos)
        self.update_readouts()

    def dknob(self, var):
        return self._optics[var.knob.param][1]

    # manage 'active' state

    started = False

    def start(self):
        if not self.started:
            self.started = True
            self.backup()
            self.timer = QtCore.QTimer()
            self.timer.timeout.connect(self.update_readouts)
            self.timer.start(1000)

    def stop(self):
        if self.started:
            self.started = False
            self.restore()
            self.timer.timeout.disconnect(self.update_readouts)
            self.timer.stop()
            self.timer = None

    def backup(self):
        self.backup_twiss_args = self.model.twiss_args
        self.backup_strengths = [
            (mknob, mknob.read())
            for mknob, _ in self._knobs.values()
        ]

    def restore(self):
        self.model.twiss_args = self.backup_twiss_args
        for mknob, value in self.backup_strengths:
            mknob.write(value)

    def update_readouts(self):
        self.readouts[:] = [
            MonitorReadout(monitor, self.control.read_monitor(monitor))
            for monitor in self.monitors
        ]

    # computations

    def fit_particle_orbit(self):
        utool = self.utool
        records = self.readouts
        self.model.madx.command.select(flag='interpolate', clear=True)
        secmaps = self.model.get_transfer_maps([r.monitor for r in records])
        secmaps = list(itertools.accumulate(secmaps, lambda a, b: np.dot(b, a)))

        (x, px, y, py), chi_squared, singular = fit_initial_orbit(*[
            (secmap[:,:6], secmap[:,6], (utool.strip_unit('x', record.x),
                                         utool.strip_unit('y', record.y)))
            for record, secmap in zip(records, secmaps)
        ])
        return utool.dict_add_unit({
            'x': x, 'px': px,
            'y': y, 'py': py,
        }), chi_squared, singular

    def compute_steerer_corrections(self, init_orbit):

        """
        Compute corrections for the x_steerers, y_steerers.

        :param dict init_orbit: initial conditions as returned by the fit
        """

        # construct initial conditions
        init_twiss = {}
        init_twiss.update(self.model.twiss_args)
        init_twiss.update(init_orbit)
        self.model.twiss_args = init_twiss

        # match final conditions
        match_names = [v.knob.param for v in self.variables]
        constraints = [
            dict(range=c.elem.Name, **self.utool.dict_strip_unit({
                c.axis: c.value
            }))
            for c in self.constraints
        ]
        self.model.madx.command.select(flag='interpolate', clear=True)
        self.model.madx.match(
            sequence=self.model.sequence.name,
            vary=match_names,
            method=('jacobian', {}),
            weight={'x': 1e3, 'y':1e3, 'px':1e2, 'py':1e2},
            constraints=constraints,
            twiss_init=self.utool.dict_strip_unit(init_twiss))
        self.model.twiss.invalidate()

        # return corrections
        return [(mknob, mknob.read(), dknob, dknob.read())
                for v in self.variables
                for mknob, dknob in [self._optics[v.knob.param]]]


def display_name(name):
    return name.upper()

def format_knob(widget, var, index):
    dknob = widget.corrector.dknob(var)
    return dknob.param

def format_final(widget, var, index):
    dknob = widget.corrector.dknob(var)
    ui_unit = getattr(dknob.param, 'ui_unit', dknob.unit)
    return tounit(var.knob.to(dknob.attr, var.value), ui_unit)

def format_initial(widget, var, index):
    dknob = widget.corrector.dknob(var)
    ui_unit = getattr(dknob.param, 'ui_unit', dknob.unit)
    return tounit(var.knob.to(dknob.attr, var.design), ui_unit)
    #return dknob.read()

def set_constraint_value(widget, c, i, value):
    widget.corrector.constraints[i] = Constraint(c.elem, c.pos, c.axis, value)

class CorrectorWidget(QtGui.QWidget):

    steerer_corrections = None

    ui_file = 'mgm_dialog.ui'

    readout_columns = [
        ColumnInfo("Monitor", 'monitor', resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("X", 'x', resize=QtGui.QHeaderView.ResizeToContents),
        ColumnInfo("Y", 'y', resize=QtGui.QHeaderView.ResizeToContents),
    ]

    constraint_columns = [
        ColumnInfo("Element", lambda c: c.elem.Name,
                   resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("Param", 'axis', resize=QtGui.QHeaderView.ResizeToContents),
        ExtColumnInfo("Value", 'value', set_constraint_value,
                      resize=QtGui.QHeaderView.ResizeToContents),
    ]

    steerer_columns = [
        ExtColumnInfo("Steerer", format_knob, resize=QtGui.QHeaderView.Stretch),
        ExtColumnInfo("Initial", format_initial, resize=QtGui.QHeaderView.ResizeToContents),
        ExtColumnInfo("Final", format_final, resize=QtGui.QHeaderView.ResizeToContents),
    ]

    def __init__(self, corrector):
        super().__init__()
        uic.loadUi(resource_filename(__name__, self.ui_file), self)
        self.corrector = corrector
        self.corrector.start()
        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    def closeEvent(self, event):
        self.corrector.stop()

    shown = False
    def showEvent(self, event):
        self.shown = False

    def hideEvent(self, event):
        self.shown = True

    def on_execute_corrections(self):
        """Apply calculated corrections."""
        self.corrector.restore()
        for mknob, mval, dknob, dval in self.steerer_corrections:
            mknob.write(mval)
            dknob.write(mknob.to(dknob.attr, mval))
        self.corrector.apply()
        self.corrector.backup()
        self.corrector.control._plugin.execute()
        self.corrector.model.twiss.invalidate()

    def init_controls(self):
        for tab in (self.mon_tab, self.con_tab, self.var_tab):
            tab.horizontalHeader().setHighlightSections(False)
            tab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
            tab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        corr = self.corrector
        self.mon_tab.set_columns(self.readout_columns, corr.readouts, self)
        self.var_tab.set_columns(self.steerer_columns, corr.variables, self)
        self.con_tab.set_columns(self.constraint_columns, corr.constraints, self)
        self.combo_config.addItems(list(self.corrector.configs))
        self.combo_config.setCurrentText(self.corrector.active)
        fit_button(self.btn_edit_conf)

    def set_initial_values(self):
        self.update_fit_button.setFocus()
        self.update_fit()
        self.radio_mode_xy.setChecked(True)

    def connect_signals(self):
        self.update_fit_button.clicked.connect(self.update_fit)
        self.execute_corrections.clicked.connect(self.on_execute_corrections)
        self.combo_config.currentIndexChanged.connect(self.on_change_config)
        self.btn_edit_conf.clicked.connect(self.edit_config)
        self.radio_mode_x.clicked.connect(partial(self.on_change_mode, 'x'))
        self.radio_mode_y.clicked.connect(partial(self.on_change_mode, 'y'))
        self.radio_mode_xy.clicked.connect(partial(self.on_change_mode, 'xy'))

    def update_fit(self):
        """Calculate initial positions / corrections."""
        twiss_init = None
        if len(self.corrector.readouts) >= 2:
            self.corrector.control.read_all()
            self.corrector.model.twiss_args = self.corrector.backup_twiss_args
            init_orbit, chi_squared, singular = \
                self.corrector.fit_particle_orbit()
            if not singular:
                twiss_init = init_orbit

        if twiss_init is None or not self.corrector.variables:
            self.steerer_corrections = None
            self.execute_corrections.setEnabled(False)
            return
        self.steerer_corrections = \
            self.corrector.compute_steerer_corrections(twiss_init)
        self.execute_corrections.setEnabled(True)
        # update table view
        self.corrector.variables[:] = [
            variable_update(self.corrector, v) for v in self.corrector.variables]
        self.var_tab.resizeColumnToContents(0)

    def on_change_config(self, index):
        name = self.combo_config.itemText(index)
        self.corrector.setup(name, self.corrector.mode)

    def on_change_mode(self, dirs):
        self.corrector.setup(self.corrector.active, dirs)

        # TODO: make 'optimal'-column in var_tab editable and update
        #       self.execute_corrections.setEnabled according to its values

    def edit_config(self):
        dialog = EditConfigDialog(self.corrector.model, self.corrector)
        dialog.exec_()


class EditConfigDialog(QtGui.QDialog):

    def __init__(self, model, matcher):
        super().__init__()
        self.model = model
        self.matcher = matcher
        self.textbox = QtGui.QPlainTextEdit()
        self.textbox.setFont(monospace(10))
        buttons = QtGui.QDialogButtonBox()
        buttons.addButton(buttons.Ok).clicked.connect(self.accept)
        buttons.addButton(buttons.Apply).clicked.connect(self.apply)
        buttons.addButton(buttons.Cancel).clicked.connect(self.reject)
        self.setLayout(VBoxLayout([self.textbox, buttons]))
        self.setSizeGripEnabled(True)
        self.resize(QtCore.QSize(600,400))
        self.setWindowTitle(self.model.filename)

        with open(model.filename) as f:
            text = f.read()
        self.textbox.appendPlainText(text)

    def accept(self):
        if self.apply():
            super().accept()

    def apply(self):
        text = self.textbox.toPlainText()
        try:
            data = yaml.safe_load(text)
        except yaml.error.YAMLError:
            QtGui.QMessageBox.critical(
                self,
                'Syntax error in YAML document',
                'There is a syntax error in the YAML document, please edit.')
            return False

        configs = data.get('multi_grid')
        if not configs:
            QtGui.QMessageBox.critical(
                self,
                'No config defined',
                'No multi grid configuration defined.')
            return False

        with open(self.model.filename, 'w') as f:
            f.write(text)

        self.matcher.configs = configs
        self.model.data['multi_grid'] = configs

        if self.matcher.active in configs:
            self.matcher.setup(self.matcher.active)
        else:
            self.matcher.setup(next(iter(configs)))

        return True
