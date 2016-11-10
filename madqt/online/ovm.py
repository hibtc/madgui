# encoding: utf-8
"""
Utilities for the optic variation method (Optikvarianzmethode) for beam
alignment.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from pkg_resources import resource_filename

import numpy as np

from madqt.qt import Qt, QtCore, QtGui, uic
from madqt.core.app import safe_timer
from madqt.core.unit import get_unit, strip_unit, get_raw_label
from madqt.widget.tableview import ColumnInfo
from madqt.util.layout import VBoxLayout
from madqt.util.collections import List


# TODO: automatically switch to "orbit" plot and display with current
#       self.computed_twiss_initial)

# TODO: use UI units

__all__ = [
    'OpticVariationMethod',
    'SelectWidget',
    'SummaryWidget',
    'StepWidget',
]


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


def isclose(q1, q2):
    m1 = strip_unit(q1, get_unit(q1))
    m2 = strip_unit(q2, get_unit(q1))
    return np.isclose(m1, m2)


def allclose(q1, q2):
    return all(isclose(a, b) for a, b in zip(q1, q2))


class RecordInfo(object):

    def __init__(self, optics, beam, sectormap):
        self.optics = tuple(optics)
        self.beam = beam
        self.sectormap = sectormap

    @property
    def kL_1(self):
        return self.optics[0]

    @property
    def kL_2(self):
        return self.optics[1]

    @property
    def x(self):
        return self.beam['posx']

    @property
    def y(self):
        return self.beam['posy']


class OpticVariationMethod(object):

    """
    Data for the optic variation method.
    """

    def __init__(self, control, mon, qps, hst, vst):
        self.control = control
        self.mon = mon
        self.qps = qps
        self.hst = hst
        self.vst = vst
        self.utool = control._segment.universe.utool
        self.segment = control._segment
        self.records = List()

    def get_monitor(self):
        return self.control.get_element(self.mon)

    def get_qp(self, index):
        return self.control.get_element(self.qps[index])

    def get_transfer_map(self):
        return self.segment.get_transfer_map(
            self.segment.start,
            self.segment.get_element_info(self.mon))

    def record_measurement(self, index=None):
        monitor = self.get_monitor()
        qps = (self.get_qp(0), self.get_qp(1))

        dvm_data = [qp.dvm_converter.to_standard(qp.dvm_backend.get())
                    for qp in qps]

        # update MAD backend
        for qp, data in zip(qps, dvm_data):
            qp.mad_backend.set(qp.mad_converter.to_backend(data))

        optics = tuple(data['kL'] for data in dvm_data)
        beam = monitor.dvm_converter.to_standard(monitor.dvm_backend.get())
        record = RecordInfo(optics, beam, self.get_transfer_map())
        if index is None:
            self.records.append(record)
        else:
            self.records[index] = record

    def clear(self):
        self.records.clear()

    def compute_initial_position(self):
        x, px, y, py = _compute_initial_position(
            (r.sectormap, self._strip_sd_pair(r.beam))
            for r in self.records)
        return self.utool.dict_add_unit({
            'x': x, 'px': px,
            'y': y, 'py': py,
        })

    def compute_steerer_corrections(self, init_pos, xpos, ypos):

        strip_unit = self.utool.strip_unit

        steerer_names = []
        if xpos is not None: steerer_names.extend(self.hst)
        if ypos is not None: steerer_names.extend(self.vst)
        steerer_elems = [self.control.get_element(v) for v in steerer_names]

        # backup  MAD-X values
        steerer_values = [el.mad_backend.get() for el in steerer_elems]

        match_names = [list(el.mad_backend._lval.values())[0] for el in steerer_elems]

        # compute initial condition
        init_twiss = {}
        init_twiss.update(self.segment.twiss_args)
        init_twiss.update(init_pos)
        self.segment.twiss_args = init_twiss

        # match final conditions
        constraints = []
        if xpos is not None:
            constraints.extend([
                {'range': self.mon, 'x': strip_unit('x', xpos)},
                {'range': self.mon, 'px': 0},
            ])
        if ypos is not None:
            constraints.extend([
                {'range': self.mon, 'y': strip_unit('y', ypos)},
                {'range': self.mon, 'py': 0},
            ])
        # TODO: also set betx, bety unchanged?
        self.segment.madx.match(
            sequence=self.segment.sequence.name,
            vary=match_names,
            constraints=constraints,
            twiss_init=self.utool.dict_strip_unit(init_twiss))
        self.segment.retrack()

        # save kicker corrections
        steerer_corrections = [
            (el, el.mad_backend.get(), el.dvm_backend.get())
            for el in steerer_elems
        ]

        # restore MAD-X values
        for el, val in zip(steerer_elems, steerer_values):
            el.mad_backend.set(val)

        return steerer_corrections

    def _strip_sd_pair(self, sd_values, prefix='pos'):
        strip_unit = self.utool.strip_unit
        return (strip_unit('x', sd_values[prefix + 'x']),
                strip_unit('y', sd_values[prefix + 'y']))


def _compute_initial_position(records):
    """
    Compute initial beam position from two monitor read-outs at different
    quadrupole settings.

    Call as follows:

        >>> _compute_initial_position([(A, a), (B, b), …])

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
    return np.linalg.lstsq(M, m)[0][:4]


class SelectWidget(QtGui.QWidget):

    """
    Select elements for "optik-varianz" method.
    """

    # TODO: integrate into wizard?

    def __init__(self, elements, config):
        super(SelectWidget, self).__init__()
        uic.loadUi(resource_filename(__name__, 'ovm_select.ui'), self)
        self.choice_monitor.currentIndexChanged.connect(self.on_change_monitor)
        self.ctrl_qps = (self.choice_qp1, self.choice_qp2)
        self.ctrl_hst = (self.choice_hsteer1, self.choice_hsteer2)
        self.ctrl_vst = (self.choice_vsteer1, self.choice_vsteer2)
        self.set_elements(elements, config)

    def set_elements(self, elements, config):
        """Set valid elements and default choices."""
        self.config = config if config else {}
        self.elements = elements
        self.elem_mon = [el for el in elements if el['type'].endswith('monitor')]
        self.elem_qps = [el for el in elements if el['type'] == 'quadrupole']
        self.elem_dip = [el for el in elements if _is_steerer(el)]
        self.choice_monitor.addItems(el_names(self.elem_mon))
        for ctrl in self.ctrl_qps:
            ctrl.addItems(el_names(self.elem_qps))
        for ctrl in self.ctrl_hst + self.ctrl_vst:
            ctrl.addItems(el_names(self.elem_dip))
        if config:
            sel = max(self.choice_monitor.findText(display_name(mon))
                      for mon in config)
        else:
            sel = len(self.elem_mon) - 1
        self.choice_monitor.setCurrentIndex(sel)

    def on_change_monitor(self):
        """Update QP/steerer choices when selecting a configured monitor."""
        conf = self.config.get(self.choice_monitor.currentText().upper(), {})
        elem_ctrls = (self.ctrl_qps, self.ctrl_hst, self.ctrl_vst)
        conf_sects = ('qp', 'h-steerer', 'v-steerer')
        # handle sections individually to allow partial config:
        for ctrls, sect in zip(elem_ctrls, conf_sects):
            for ctrl, name in zip(ctrls, conf.get(sect, ())):
                ctrl.setCurrentIndex(ctrl.findText(display_name(name)))

    def get_data(self):
        """Get current monitor/QP/H-/V-steerer choices."""
        get_choice = lambda ctrl: ctrl.currentText().lower()
        mon = get_choice(self.choice_monitor)
        qps = tuple(map(get_choice, self.ctrl_qps))
        hst = tuple(map(get_choice, self.ctrl_hst))
        vst = tuple(map(get_choice, self.ctrl_vst))
        return mon, qps, hst, vst

    def set_data(self, choices):
        # TODO: check config (length/content of individual fields)
        # TODO: remember selection
        pass

    def validate(self):
        get_index = lambda ctrl: ctrl.currentIndex()
        sel_mon = get_index(self.choice_monitor)
        sel_qp = tuple(map(get_index, self.ctrl_qps))
        sel_st = tuple(map(get_index, self.ctrl_hst + self.ctrl_vst))
        def _at(sel, elems):
            if sel == -1:
                raise ValueError
            return elems[sel]['at']
        try:
            at_mon = _at(sel_mon, self.elem_mon)
            at_qp = [_at(sel, self.elem_qps) for sel in sel_qp]
            at_st = [_at(sel, self.elem_dip) for sel in sel_st]
        except ValueError:
            return False
        return all(at <= at_mon for at in at_qp + at_st)


class ParameterInfo(object):

    def __init__(self, param, value, current=None):
        self.name = param
        self.value = value
        self.current = current


class OVM_Widget(QtGui.QWidget):

    records_columns = [
        ColumnInfo("QP1", 'kL_1', QtGui.QHeaderView.Stretch),
        ColumnInfo("QP2", 'kL_2'),
        ColumnInfo("x", 'x'),
        ColumnInfo("y", 'y'),
    ]

    twiss_columns = [
        ColumnInfo("Param", 'name'),
        ColumnInfo("Value", 'value'),
    ]

    steerer_columns = [
        ColumnInfo("Steerer", 'name'),
        ColumnInfo("Optimal", 'value'),
        ColumnInfo("Current", 'current'),
    ]

    num_focus_levels = 6
    computed_twiss_initial = None
    steerer_corrections = None
    update_record_index = None

    def __init__(self, ovm):
        super(OVM_Widget, self).__init__()
        uic.loadUi(resource_filename(__name__, 'ovm_dialog.ui'), self)

        self.ovm = ovm
        # init controls…

        # …input group
        focus_choices = ["Focus {}".format(i+1)
                         for i in range(self.num_focus_levels)]
        self.focus_choice.addItems(focus_choices)
        self.focus_choice.setCurrentIndex(0)
        qp1 = self.ovm.get_qp(0)
        qp2 = self.ovm.get_qp(1)
        par1 = qp1.dvm_converter.param_info['kL']
        par2 = qp2.dvm_converter.param_info['kL']
        self.input_qp1_label.setText(par1.name + ':')
        self.input_qp2_label.setText(par2.name + ':')
        self.input_qp1_value.unit = par1.ui_unit
        self.input_qp2_value.unit = par2.ui_unit
        self.displ_qp1_value.unit = par1.ui_unit
        self.displ_qp2_value.unit = par2.ui_unit
        beam = self.ovm.get_monitor().dvm_backend.get()
        self.x_target_value.unit = get_unit(beam['posx'])
        self.y_target_value.unit = get_unit(beam['posx'])
        self.x_target_value.value = 0
        self.y_target_value.value = 0

        # …result groups
        # TODO: change records_columns names?
        self.records_table.set_columns(self.records_columns)
        self.twiss_table.set_columns(self.twiss_columns)
        self.corrections_table.set_columns(self.steerer_columns)
        self.records_table.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.records_table.horizontalHeader().setHighlightSections(False)

        # …update button states
        self.ovm.records.update_after.connect(self.update_clear_button)
        self.ovm.records.update_after.connect(self.update_record_button)
        self.displ_qp1_value.valueChanged.connect(self.update_record_button)
        self.displ_qp2_value.valueChanged.connect(self.update_record_button)
        # self.execute_corrections is updated in self.update_corrections()

        # connect signals
        # …perform action upon explicit user request
        self.load_preset_execute.clicked.connect(self.on_load_preset_execute)
        self.qp_settings_execute.clicked.connect(self.on_qp_settings_execute)
        self.qp_settings_record.clicked.connect(self.on_qp_settings_record)
        self.clear_records.clicked.connect(self.ovm.clear)
        self.execute_corrections.clicked.connect(self.on_execute_corrections)

        # …update records display
        self.ovm.records.mirror(self.records_table.rows)

        # …update steerer calculations when changing the target values:
        self.x_target_value.editingFinished.connect(self.update_corrections)
        self.y_target_value.editingFinished.connect(self.update_corrections)
        self.x_target_check.toggled.connect(self.update_corrections)
        self.y_target_check.toggled.connect(self.update_corrections)

        # …at least one target has to be on
        self.x_target_check.toggled.connect(
            lambda checked: self.y_target_check.setChecked(not checked))
        self.y_target_check.toggled.connect(
            lambda checked: self.x_target_check.setChecked(not checked))

        # …update beam initial conditions, when records have changed
        self.ovm.records.update_after.connect(
            lambda *args: self.update_twiss())

        # TODO:
        # - self.twiss_table.valueChanged.connect(self.update_steerer)
        # - handle DELETE keypress in recorded optics
        # - select monitor in beam group?

        # set up regular updates for tracking control-system values
        self.update_csys_values()
        self.update_csys_values_timer = QtCore.QTimer()
        self.update_csys_values_timer.timeout.connect(self.update_csys_values)
        self.update_csys_values_timer.start(100)

        # load initial values:
        self._load_csys_qp_value(0, self.input_qp1_value)
        self._load_csys_qp_value(1, self.input_qp2_value)
        self.input_qp1_value.selectAll()
        self.focus_choice.setCurrentIndex(3)
        self.records_table.rows = ovm.records

    def on_load_preset_execute(self):
        """Update focus level and automatically load QP values."""
        focus = self.focus_choice.currentIndex() + 1
        if focus == 0:
            return
        # TODO: this should be done with a more generic API
        # TODO: do this without beamoptikdll to decrease the waiting time
        dvm = self.ovm.control._plugin._dvm
        values, channels = dvm.GetMEFIValue()
        vacc = dvm.GetSelectedVAcc()
        if focus != channels.focus:
            dvm.SelectMEFI(vacc, *channels._replace(focus=focus))
        self._load_csys_qp_value(0, self.input_qp1_value)
        self._load_csys_qp_value(1, self.input_qp2_value)
        if focus != channels.focus:
            dvm.SelectMEFI(vacc, *channels)

    def on_qp_settings_record(self):
        self.ovm.record_measurement(self.update_record_index)

    def on_qp_settings_execute(self):
        """Write QP values to the control system."""
        self._write_qp_value(0, self.input_qp1_value)
        self._write_qp_value(1, self.input_qp2_value)
        self.ovm.control._plugin.execute()

    def _write_qp_value(self, index, ctrl):
        """Transmit the value of a single QP to the control system."""
        qp_elem = self.ovm.get_qp(index)
        values = {'kL': ctrl.quantity}
        qp_elem.dvm_backend.set(qp_elem.dvm_converter.to_backend(values))

    def update_csys_values(self):
        # update monitor data
        data = self.ovm.get_monitor().dvm_backend.get()
        self.x_monitor_value.quantity = data['posx']
        self.y_monitor_value.quantity = data['posy']
        # update qps
        self._load_csys_qp_value(0, self.displ_qp1_value)
        self._load_csys_qp_value(1, self.displ_qp2_value)
        return data

    def _load_csys_qp_value(self, index, ctrl):
        """Get QP value from control system."""
        qp_elem = self.ovm.get_qp(index)
        data = qp_elem.dvm_backend.get()
        ctrl.set_quantity_checked(data['kL'])

    def update_clear_button(self, *args):
        self.clear_records.setEnabled(bool(self.ovm.records))

    def update_record_button(self, *args):
        current_optics = [self.displ_qp1_value.quantity,
                          self.displ_qp2_value.quantity]
        same_values = (i for i, record in enumerate(self.ovm.records)
                       if allclose(record.optics, current_optics))
        self.update_record_index = next(same_values, None)
        # self.qp_settings_record.setEnabled(self.update_record_index is None)
        new_text = "Record" if self.update_record_index is None else "Update"
        set_text(self.qp_settings_record, new_text)

    def update_twiss(self):
        """Calculate initial positions / corrections."""
        if len(self.ovm.records) >= 2:
            self.computed_twiss_initial = self.ovm.compute_initial_position()
            beaminit_rows = [
                ParameterInfo(name, value)
                for name, value in self.computed_twiss_initial.items()
            ]
        else:
            self.computed_twiss_initial = None
            beaminit_rows = []

        self.twiss_table.rows = sorted(beaminit_rows, key=lambda item: item.name)
        self.update_corrections()

    def update_corrections(self):
        pos = self.computed_twiss_initial
        xpos = self.x_target_value.quantity if self.x_target_check.isChecked() else None
        ypos = self.y_target_value.quantity if self.y_target_check.isChecked() else None
        if pos is None or (xpos is None and ypos is None):
            self.steerer_corrections = None
            self.execute_corrections.setEnabled(False)
            # TODO: always display current steerer values
            self.corrections_table.rows = []
            return
        self.steerer_corrections = self.ovm.compute_steerer_corrections(pos, xpos, ypos)
        self.execute_corrections.setEnabled(True)
        # update table view
        steerer_corrections_rows = [
            ParameterInfo(el.dvm_params[k].name, v, dvm_vals[k])
            for el, mad_vals, dvm_vals in self.steerer_corrections
            for k, v in el.mad2dvm(mad_vals).items()
        ]
        self.corrections_table.rows = steerer_corrections_rows

        # TODO: make 'optimal'-column in corrections_table editable and update
        #       self.execute_corrections.setEnabled according to its values

    def on_execute_corrections(self):
        """Apply calculated corrections."""
        for el, mad_vals, dvm_vals in self.steerer_corrections:
            el.mad_backend.set(mad_vals)
            el.dvm_backend.set(el.mad2dvm(mad_vals))
        self.ovm.control._plugin.execute()
        self.ovm.segment.retrack()
