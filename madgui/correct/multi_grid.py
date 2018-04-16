"""
Multi grid correction method.
"""

# TODO:
# - use CORRECT command from MAD-X rather than custom numpy method?
# - combine with optic variation method

from functools import partial
import itertools

import numpy as np
import yaml

from madgui.qt import QtCore, QtGui, load_ui

from madgui.core.unit import to_ui, from_ui, ui_units
from madgui.util.collections import List
from madgui.util.layout import VBoxLayout, HBoxLayout
from madgui.util.qt import fit_button, monospace
from madgui.widget.tableview import ColumnInfo, ExtColumnInfo
from madgui.widget.edit import LineNumberBar
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
        knobs = control.get_knobs()
        self._optics = {mknob.param: (mknob, dknob) for mknob, dknob in knobs}
        self._knobs = {mknob.el_name: (mknob, dknob) for mknob, dknob in knobs}
        self.backup()
        # save elements
        self.design_values = {}
        self.monitors = List()
        self.readouts = List()
        QtCore.QTimer.singleShot(0, partial(control._frame.open_graph, 'orbit'))

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
            Constraint(elements[target], elements[target].position, key, float(value))
            for target, values in targets.items()
            for key, value in values.items()
            if key[-1] in dirs
        ], key=lambda c: c.pos)
        self.variables[:] = sorted([
            variable_from_knob(self, self._knobs[el.lower()][0])
            for el in steerers
        ], key=lambda v: v.pos)

    def dknob(self, var):
        return self._optics[var.knob.param][1]

    # manage 'active' state

    started = False

    def start(self):
        if not self.started:
            self.started = True
            self.backup()

    def stop(self):
        if self.started:
            self.started = False
            self.restore()

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

    def update(self):
        self.update_readouts()
        self.update_fit()

    def update_readouts(self):
        self.readouts[:] = [
            # NOTE: this triggers model._retrack in stub!
            MonitorReadout(monitor, self.control.read_monitor(monitor))
            for monitor in self.monitors
        ]

    def update_fit(self):
        self.fit_results = None
        if len(self.readouts) < 2:
            return
        self.control.read_all()
        self.model.twiss_args = self.backup_twiss_args
        init_orbit, chi_squared, singular = \
            self.fit_particle_orbit()
        if singular:
            return
        init_twiss = {}
        init_twiss.update(self.model.twiss_args)
        init_twiss.update(init_orbit)
        self.fit_results = init_orbit
        self.model.twiss_args = init_twiss
        self.model.twiss.invalidate()

    # computations

    def fit_particle_orbit(self):
        records = self.readouts
        self.model.madx.command.select(flag='interpolate', clear=True)
        secmaps = self.model.get_transfer_maps([r.monitor for r in records])
        secmaps = list(itertools.accumulate(secmaps, lambda a, b: np.dot(b, a)))

        (x, px, y, py), chi_squared, singular = fit_initial_orbit(*[
            (secmap[:,:6], secmap[:,6], (record.x, record.y))
            for record, secmap in zip(records, secmaps)
        ])
        return {
            'x': x, 'px': px,
            'y': y, 'py': py,
        }, chi_squared, singular

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

        for name, expr in self.selected.get('assign', {}).items():
            self.model.madx.input(name.replace('->', ', ') + ':=' + expr + ';')
        knobs = self.control.get_knobs()
        self._optics = {mknob.param: (mknob, dknob) for mknob, dknob in knobs}
        self._knobs = {mknob.el_name: (mknob, dknob) for mknob, dknob in knobs}
        steerers = sum([self.selected['steerers'][d] for d in self.mode], [])
        self.variables[:] = sorted([
            variable_from_knob(self, self._knobs[el.lower()][0])
            for el in steerers
        ], key=lambda v: v.pos)

        # match final conditions
        blacklist = [v.lower() for v in self.model.data.get('readonly', ())]
        match_names = {v.knob.param for v in self.variables
                       if v.knob.param.lower() not in blacklist}
        constraints = [
            dict(range=c.elem.node_name, **{c.axis: from_ui(c.axis, c.value)})
            for c in self.constraints
        ]
        for name, expr in self.selected.get('assign', {}).items():
            self.model.madx.input(name.replace('->', ', ') + ':=' + expr + ';')
        self.model.madx.command.select(flag='interpolate', clear=True)
        self.model.madx.match(
            sequence=self.model.sequence.name,
            vary=match_names,
            method=('jacobian', {}),
            weight={'x': 1e3, 'y':1e3, 'px':1e2, 'py':1e2},
            constraints=constraints,
            **init_twiss)
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
    return to_ui(dknob.attr, var.value)

def format_initial(widget, var, index):
    dknob = widget.corrector.dknob(var)
    return to_ui(dknob.attr, var.design)
    #return dknob.read()

def format_unit(widget, var, index):
    dknob = widget.corrector.dknob(var)
    return ui_units.label(dknob.attr)

def set_constraint_value(widget, c, i, value):
    widget.corrector.constraints[i] = Constraint(c.elem, c.pos, c.axis, value)

class CorrectorWidget(QtGui.QWidget):

    steerer_corrections = None

    ui_file = 'mgm_dialog.ui'

    readout_columns = [
        ColumnInfo("Monitor", 'monitor', resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("X", 'x', convert=True),
        ColumnInfo("Y", 'y', convert=True),
        ColumnInfo("Unit", lambda item: ui_units.label('x'),
                   resize=QtGui.QHeaderView.ResizeToContents),
    ]

    constraint_columns = [
        ColumnInfo("Element", lambda c: c.elem.node_name,
                   resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("Param", 'axis', resize=QtGui.QHeaderView.ResizeToContents),
        ExtColumnInfo("Value", 'value', set_constraint_value,
                      convert='axis',
                      resize=QtGui.QHeaderView.ResizeToContents),
        ColumnInfo("Unit", lambda item: ui_units.label(item.axis),
                   resize=QtGui.QHeaderView.ResizeToContents),
    ]

    steerer_columns = [
        ExtColumnInfo("Steerer", format_knob, resize=QtGui.QHeaderView.Stretch),
        ExtColumnInfo("Initial", format_initial, resize=QtGui.QHeaderView.ResizeToContents),
        ExtColumnInfo("Final", format_final, resize=QtGui.QHeaderView.ResizeToContents),
        ExtColumnInfo("Unit", format_unit, resize=QtGui.QHeaderView.ResizeToContents),
    ]

    def __init__(self, corrector):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
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
        twiss_args = self.corrector.model.twiss_args
        self.corrector.restore()
        for mknob, mval, dknob, dval in self.steerer_corrections:
            mknob.write(mval)
            dknob.write(mval)
        self.corrector.apply()
        self.corrector.backup()
        self.corrector.control._plugin.execute()
        self.corrector.model.twiss_args = twiss_args
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
        self.radio_mode_xy.setChecked(True)
        self.corrector.update()

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
        self.corrector.update()

        if not self.corrector.fit_results or not self.corrector.variables:
            self.steerer_corrections = None
            self.execute_corrections.setEnabled(False)
            return
        self.steerer_corrections = \
            self.corrector.compute_steerer_corrections(self.corrector.fit_results)
        self.execute_corrections.setEnabled(True)
        # update table view
        self.corrector.variables[:] = [
            variable_update(self.corrector, v) for v in self.corrector.variables]
        self.var_tab.resizeColumnToContents(0)

    def on_change_config(self, index):
        name = self.combo_config.itemText(index)
        self.corrector.setup(name, self.corrector.mode)
        self.corrector.update()

    def on_change_mode(self, dirs):
        self.corrector.setup(self.corrector.active, dirs)
        self.corrector.update()

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
        self.textbox.setFont(monospace())
        self.linenos = LineNumberBar(self.textbox)
        buttons = QtGui.QDialogButtonBox()
        buttons.addButton(buttons.Ok).clicked.connect(self.accept)
        buttons.addButton(buttons.Apply).clicked.connect(self.apply)
        buttons.addButton(buttons.Cancel).clicked.connect(self.reject)
        self.setLayout(VBoxLayout([
            HBoxLayout([self.linenos, self.textbox], tight=True),
            buttons,
        ]))
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

        conf = configs.get(self.matcher.active, next(iter(configs)))
        self.matcher.setup(conf)
        self.matcher.update()

        return True
