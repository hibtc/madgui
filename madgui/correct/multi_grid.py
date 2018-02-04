"""
Multi grid correction method.
"""

# TODO:
# - allow more than 2 monitors
# - use CORRECT command from MAD-X rather than custom numpy method?
# - combine with optic variation method

from pkg_resources import resource_filename
import itertools

import numpy as np

from madgui.qt import QtCore, QtGui, uic

from madgui.core.unit import tounit, units
from madgui.util.collections import List
from madgui.widget.tableview import ColumnInfo, ExtColumnInfo
from madgui.correct.orbit import fit_initial_orbit

from .match import Matcher, Constraint, variable_from_knob, variable_update


class MonitorReadout:

    def __init__(self, monitor, orbit):
        self.monitor = monitor
        self.x = orbit['posx']
        self.y = orbit['posy']


class ParameterInfo:

    def __init__(self, param, value):
        self.name = param
        self.value = value


class Corrector(Matcher):

    """
    Single target orbit correction via optic variation.
    """

    def __init__(self, control, monitors, targets, steerers):
        super().__init__(control._model, None)
        self.control = control
        self.control.read_all()
        self.utool = control._model.utool
        knobs = control.get_knobs()
        self._optics = {mknob.param: (mknob, dknob) for mknob, dknob in knobs}
        self._knobs = {mknob.el_name: (mknob, dknob) for mknob, dknob in knobs}
        # save elements
        elements = self.model.elements
        self.design_values = {}
        self.monitors = List(list(monitors))
        self.readouts = List()
        self.fit_results = List()

        self.constraints.extend(sorted([
            Constraint(elements[target], elements[target].At, key,
                       self.utool.add_unit(key, value))
            for target, values in targets.items()
            for key, value in values.items()
        ], key=lambda c: c.pos))

        self.variables.extend(sorted([
            variable_from_knob(self, self._knobs[el.lower()][0])
            for el in steerers
        ], key=lambda v: v.pos))

        control._frame.open_graph('orbit')
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

    initial_particle_orbit = None
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

    fit_columns = [
        ColumnInfo("Param", 'name', resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("Value", 'value', resize=QtGui.QHeaderView.ResizeToContents),
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

    def _update_fit_table(self, initial_particle_orbit, beaminit_rows):
        self.initial_particle_orbit = initial_particle_orbit
        self.corrector.fit_results[:] = beaminit_rows
        self.fit_tab.resizeColumnToContents(0)
        self.update_corrections()

    def update_corrections(self):
        init = self.initial_particle_orbit

        if init is None or not self.corrector.variables:
            self.steerer_corrections = None
            self.execute_corrections.setEnabled(False)
            return
        self.steerer_corrections = \
            self.corrector.compute_steerer_corrections(init)
        self.execute_corrections.setEnabled(True)
        # update table view
        self.corrector.variables[:] = [
            variable_update(self.corrector, v) for v in self.corrector.variables]
        self.var_tab.resizeColumnToContents(0)

        # TODO: make 'optimal'-column in var_tab editable and update
        #       self.execute_corrections.setEnabled according to its values

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
        for tab in (self.mon_tab, self.con_tab, self.var_tab, self.fit_tab):
            tab.horizontalHeader().setHighlightSections(False)
            tab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
            tab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        corr = self.corrector
        self.mon_tab.set_columns(self.readout_columns, corr.readouts, self)
        self.var_tab.set_columns(self.steerer_columns, corr.variables, self)
        self.con_tab.set_columns(self.constraint_columns, corr.constraints, self)
        self.fit_tab.set_columns(self.fit_columns, corr.fit_results, self)

    def set_initial_values(self):
        self.update_fit_button.setFocus()
        self.update_fit()

    def connect_signals(self):
        self.update_fit_button.clicked.connect(self.update_fit)
        self.execute_corrections.clicked.connect(self.on_execute_corrections)

    def update_fit(self):
        """Calculate initial positions / corrections."""
        if len(self.corrector.readouts) < 2:
            self._update_fit_table(None, [])
            return
        self.corrector.control.read_all()
        self.corrector.model.twiss_args = self.corrector.backup_twiss_args

        init_orbit, chi_squared, singular = \
            self.corrector.fit_particle_orbit()
        if singular:
            self._update_fit_table(None, [
                ParameterInfo("", "SINGULAR MATRIX")])
            return
        x = tounit(init_orbit['x'], 1*units.mm)
        y = tounit(init_orbit['y'], 1*units.mm)
        px = init_orbit['px']
        py = init_orbit['py']
        self._update_fit_table(init_orbit, [
            #ParameterInfo("red χ²", chi_squared),
            ParameterInfo('x', x),
            ParameterInfo('y', y),
            ParameterInfo('px/p₀', px),
            ParameterInfo('py/p₀', py),
        ])
