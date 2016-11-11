# encoding: utf-8
"""
Shared utilities for orbit correction.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from abc import abstractmethod

from pkg_resources import resource_filename

import numpy as np
from six import string_types as basestring

from madqt.qt import QtGui, uic

from madqt.core.unit import tounit
from madqt.util.collections import List
from madqt.widget.tableview import ColumnInfo


class OrbitRecord(object):

    def __init__(self, monitor, orbit, sectormap, optics):
        self.monitor = monitor
        self.orbit = orbit
        self.sectormap = sectormap
        self.optics = optics

    @property
    def x(self):
        return self.orbit['posx']

    @property
    def y(self):
        return self.orbit['posy']


class ParameterInfo(object):

    def __init__(self, param, value, current=None):
        self.name = param
        self.value = value
        self.current = current


class OrbitCorrectorBase(object):

    """
    Data for the optic variation method.
    """

    def __init__(self, control,
                 targets, magnets, monitors,
                 x_steerers, y_steerers):
        self.control = control
        self.utool = control._segment.universe.utool
        self.segment = control._segment
        # save elements
        self.targets = targets
        self.magnets = magnets
        self.monitors = monitors
        self.x_steerers = x_steerers
        self.y_steerers = y_steerers
        # recorded transfer maps + monitor measurements
        self.orbit_records = List()

    # access elements

    def get_element(self, name):
        if isinstance(name, basestring):
            return self.control.get_element(name)
        return name

    # access element values

    def get_info(self, elem):
        return self.get_element(elem).dvm_converter.param_info

    def get_dvm(self, elem):
        elem = self.get_element(elem)
        return elem.dvm_converter.to_standard(elem.dvm_backend.get())

    def get_mad(self, elem):
        elem = self.get_element(elem)
        return elem.mad_converter.to_standard(elem.mad_backend.get())

    def set_dvm(self, elem, data):
        elem = self.get_element(elem)
        elem.dvm_backend.set(elem.dvm_converter.to_backend(data))

    def set_mad(self, elem, data):
        elem = self.get_element(elem)
        elem.mad_backend.set(elem.mad_converter.to_backend(data))

    def get_transfer_map(self, dest, orig=None):
        # TODO: get multiple transfer maps in one TWISS call
        return self.segment.get_transfer_map(
            self.segment.start if orig is None else orig,
            self.segment.get_element_info(dest))

    def sync_csys_to_mad(self, elements):
        """Update element settings in MAD-X from control system."""
        optics = [self.get_dvm(elem) for elem in elements]
        for elem, optic in zip(elements, optics):
            self.set_mad(elem, optic)
        return optics

    # record monitor/model

    def current_orbit_records(self):
        magnet_optics = self.sync_csys_to_mad(self.magnets)
        return [
            OrbitRecord(
                monitor,
                self.get_dvm(monitor),
                self.get_transfer_map(monitor),
                magnet_optics)
            for monitor in self.monitors
        ]

    def add_orbit_records(self, records, index=None):
        if index is None:
            self.orbit_records.extend(records)
        else:
            self.orbit_records[index:index+len(records)] = records

    def clear_orbit_records(self):
        self.orbit_records.clear()

    # computations

    def fit_particle_orbit(self):
        self.fit_results = _fit_particle_orbit(
            (record.sectormap, self._strip_sd_pair(record.orbit))
            for record in self.orbit_records)
        initial_orbit, chi_squared, singular = self.fit_results
        x, px, y, py = initial_orbit
        return self.utool.dict_add_unit({
            'x': x, 'px': px,
            'y': y, 'py': py,
        }), chi_squared, singular

    def compute_steerer_corrections(self, init_orbit, design_orbit,
                                    correct_x=None, correct_y=None):

        """
        Compute corrections for the x_steerers, y_steerers.

        :param dict init_orbit: initial conditions as returned by the fit
        :param list design_orbit: design orbit at the target positions
        """

        # TODO: make this work with backends other than MAD-X…

        if correct_x is None:
            correct_x = any(('x' in orbit or 'px' in orbit)
                            for orbit in design_orbit)
        if correct_y is None:
            correct_y = any(('y' in orbit or 'py' in orbit)
                            for orbit in design_orbit)

        steerer_names = []
        if correct_x: steerer_names.extend(self.x_steerers)
        if correct_y: steerer_names.extend(self.y_steerers)
        steerer_elems = [self.get_element(elem) for elem in steerer_names]

        # backup  MAD-X values
        steerer_values_backup = [self.get_mad(el) for el in steerer_elems]

        try:
            # construct initial conditions
            init_twiss = {}
            init_twiss.update(self.segment.twiss_args)
            init_twiss.update(init_orbit)
            self.segment.twiss_args = init_twiss

            # match final conditions
            match_names = [
                name for el in steerer_elems
                for name in el.mad_backend._lval.values()
            ]
            constraints = [
                dict(range=target, **self.utool.dict_strip_unit(orbit))
                for target, orbit in zip(self.targets, design_orbit)
            ]
            self.segment.madx.match(
                sequence=self.segment.sequence.name,
                vary=match_names,
                constraints=constraints,
                twiss_init=self.utool.dict_strip_unit(init_twiss))
            self.segment.retrack()

            # return corrections
            return [(el, el.mad_backend.get(), el.dvm_backend.get())
                    for el in steerer_elems]

        # restore MAD-X values
        finally:
            for el, val in zip(steerer_elems, steerer_values_backup):
                self.set_mad(el, val)

    def _strip_sd_pair(self, sd_values, prefix='pos'):
        strip_unit = self.utool.strip_unit
        return (strip_unit('x', sd_values[prefix + 'x']),
                strip_unit('y', sd_values[prefix + 'y']))


def _is_steerer(el):
    return el['type'] == 'sbend' \
        or el['type'].endswith('kicker') \
        or el['type'] == 'multipole' and (
            el['knl'][0] != 0 or
            el['ksl'][0] != 0)


def display_name(name):
    return name.upper()


def el_names(elems):
    return [display_name(el['name']) for el in elems]


def set_text(ctrl, text):
    """Update text in a control, but avoid flicker/deselection."""
    if ctrl.text() != text:
        ctrl.setText(text)


def _fit_particle_orbit(records):
    """
    Compute initial beam position from two monitor read-outs at different
    quadrupole settings.

    Call as follows:

        >>> _fit_particle_orbit([(A, a), (B, b), …])

    where

        A, B, … are the 7D SECTORMAPs from start to the monitor.
        a, b, … are the 2D measurement vectors (x, y)

    This function solves the linear system:

            Ax = a
            Bx = b
            …

    for the 4D phase space vector x = (x, px, y, py).
    """
    AB_, ab_ = zip(*records)
    # use only the relevant submatrices:
    rows = (0,2)
    cols = (0,1,2,3,6)
    M = np.vstack([X[rows,:][:,cols] for X in AB_])
    m = np.hstack(ab_)
    # demand x[4] = m[-1] = 1
    M = np.vstack((M, np.eye(1, 5, 4)))
    m = np.hstack((m, 1))
    x, residuals, rank, singular = np.linalg.lstsq(M, m)
    return (x[:4],
            0 if len(residuals) == 0 else residuals[0],
            rank < 5)


class CorrectorWidgetBase(QtGui.QWidget):

    initial_particle_orbit = None
    steerer_corrections = None

    fit_columns = [
        ColumnInfo("Param", 'name'),
        ColumnInfo("Value", 'value'),
    ]

    steerer_columns = [
        ColumnInfo("Steerer", 'name'),
        ColumnInfo("Optimal", 'value'),
        ColumnInfo("Current", 'current'),
    ]

    def __init__(self, corrector):
        super(CorrectorWidgetBase, self).__init__()
        uic.loadUi(resource_filename(__name__, self.ui_file), self)
        self.corrector = corrector
        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    @abstractmethod
    def init_controls(self):
        pass

    @abstractmethod
    def set_initial_values(self):
        pass

    @abstractmethod
    def connect_signals(self):
        pass

    def update_records(self):
        self.records_table.rows = self.corrector.orbit_records

    def update_fit(self):
        """Calculate initial positions / corrections."""
        if len(self.corrector.orbit_records) < 2:
            self._update_fit_table(None, [])
            return
        init_orbit, chi_squared, singular = \
            self.corrector.fit_particle_orbit()
        if singular:
            self._update_fit_table(None, [
                ParameterInfo("", "SINGULAR MATRIX")])
            return
        x = tounit(init_orbit['x'], self.x_target_value.unit)
        y = tounit(init_orbit['y'], self.y_target_value.unit)
        px = init_orbit['px']
        py = init_orbit['py']
        self._update_fit_table(init_orbit, [
            ParameterInfo("red χ²", chi_squared),
            ParameterInfo('x', x),
            ParameterInfo('y', y),
            ParameterInfo('px/p₀', px),
            ParameterInfo('py/p₀', py),
        ])

    def _update_fit_table(self, initial_particle_orbit, beaminit_rows):
        self.initial_particle_orbit = initial_particle_orbit
        self.fit_table.rows = beaminit_rows
        self.fit_table.resizeColumnToContents(0)
        self.update_corrections()

    def update_corrections(self):
        init = self.initial_particle_orbit
        design = {}
        if self.x_target_check.isChecked():
            design['x'] = self.x_target_value.quantity
            design['px'] = 0
        if self.y_target_check.isChecked():
            design['y'] = self.y_target_value.quantity
            design['py'] = 0
        if init is None or not design:
            self.steerer_corrections = None
            self.execute_corrections.setEnabled(False)
            # TODO: always display current steerer values
            self.corrections_table.rows = []
            return
        self.steerer_corrections = \
            self.corrector.compute_steerer_corrections(init, [design])
        self.execute_corrections.setEnabled(True)
        # update table view
        steerer_corrections_rows = [
            ParameterInfo(el.dvm_params[k].name, v, dvm_vals[k])
            for el, mad_vals, dvm_vals in self.steerer_corrections
            for k, v in el.mad2dvm(mad_vals).items()
        ]
        self.corrections_table.rows = steerer_corrections_rows
        self.corrections_table.resizeColumnToContents(0)

        # TODO: make 'optimal'-column in corrections_table editable and update
        #       self.execute_corrections.setEnabled according to its values

    def on_execute_corrections(self):
        """Apply calculated corrections."""
        for el, mad_vals, dvm_vals in self.steerer_corrections:
            el.mad_backend.set(mad_vals)
            el.dvm_backend.set(el.mad2dvm(mad_vals))
        self.corrector.control._plugin.execute()
        self.corrector.segment.retrack()
