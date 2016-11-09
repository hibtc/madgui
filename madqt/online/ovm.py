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
from madqt.core.unit import format_quantity, strip_unit, get_raw_label
from madqt.widget.tableview import ColumnInfo
from madqt.util.layout import VBoxLayout


# TODO: use UI units

__all__ = [
    'OpticVariationMethod',
    'ProgressWizard',
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
        self.sectormap = [None, None]
        self.measurement = [None, None]

    def get_monitor(self):
        return self.control.get_element(self.mon)

    def get_qp(self, index):
        return self.control.get_element(self.qps[index])

    def get_transfer_map(self):
        return self.segment.get_transfer_map(
            self.segment.start,
            self.segment.get_element_info(self.mon))

    def record_measurement(self, index):
        monitor = self.get_monitor()
        self.sectormap[index] = self.get_transfer_map()
        self.measurement[index] = monitor.dvm_converter.to_standard(
            monitor.dvm_backend.get())

    def compute_initial_position(self):
        x, px, y, py = _compute_initial_position(
            self.sectormap[0], self._strip_sd_pair(self.measurement[0]),
            self.sectormap[1], self._strip_sd_pair(self.measurement[1]))
        return self.utool.dict_add_unit({
            'x': x, 'px': px,
            'y': y, 'py': py,
        })

    def compute_steerer_corrections(self, init_pos, xpos=0, ypos=0):

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
                {'range': self.mon, 'x': xpos},
                {'range': self.mon, 'px': 0},
            ])
        if ypos is not None:
            constraints.extend([
                {'range': self.mon, 'y': ypos},
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
            (el, el.mad_backend.get())
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


def _compute_initial_position(A, a, B, b):
    """
    Compute initial beam position from two monitor read-outs at different
    quadrupole settings.

    A, B are the 7D SECTORMAPs from start to the monitor.
    a, b are the 2D measurement vectors (x, y)

    This function solves the linear system:

            Ax = a
            Bx = b

    for the 4D phase space vector x = (x, px, y, py).
    """
    rows = (0,2)
    cols = (0,1,2,3,6)
    M1 = A[rows,:][:,cols]
    M2 = B[rows,:][:,cols]
    M3 = np.eye(1, 5, 4)
    M = np.vstack((M1, M2, M3))
    m = np.hstack((a, b, 1))
    return np.linalg.lstsq(M, m)[0][:4]


class ProgressWizard(QtGui.QWizard):

    def __init__(self, ovm):
        super(ProgressWizard, self).__init__()
        self.addPage(StepPage(ovm, "1st optic", 0))
        self.addPage(StepPage(ovm, "2nd optic", 1))
        self.addPage(SummaryPage(ovm))


class StepPage(QtGui.QWizardPage):

    def __init__(self, ovm, title, index):
        super(StepPage, self).__init__()
        self.widget = StepWidget(ovm)
        self.index = index
        self.setLayout(VBoxLayout([self.widget]))
        self.setTitle(title)
        self.update_ui_timer = QtCore.QTimer()
        self.update_ui_timer.timeout.connect(self.widget.update_ui)

    def initializePage(self):
        """
        initializePage() is called to initialize the page's contents when the
        user clicks the wizard's Next button. If you want to derive the page's
        default from what the user entered on previous pages, this is the
        function to reimplement.
        """
        self.widget.update_ui()
        self.update_ui_timer.start(100)

    def cleanupPage(self):
        """
        cleanupPage() is called to reset the page's contents when the user
        clicks the wizard's Back button.
        """
        self.initializePage()

    def validatePage(self):
        """
        validatePage() validates the page when the user clicks Next or Finish.
        It is often used to show an error message if the user has entered
        incomplete or invalid information.
        """
        self.update_ui_timer.stop()
        self.widget.ovm.record_measurement(self.index)
        return True

    def isComplete(self):
        """
        isComplete() is called to determine whether the Next and/or Finish
        button should be enabled or disabled. If you reimplement isComplete(),
        also make sure that completeChanged() is emitted whenever the complete
        state changes.
        """
        # TODO: should use validators of input controls and ensure that second
        # optic differs from the first
        return True


class SummaryPage(QtGui.QWizardPage):

    def __init__(self, ovm):
        super(SummaryPage, self).__init__()
        self.widget = SummaryWidget(ovm)
        self.setLayout(VBoxLayout([self.widget]))
        self.setTitle("Confirm steerer corrections")

    def initializePage(self):
        """
        initializePage() is called to initialize the page's contents when the
        user clicks the wizard's Next button. If you want to derive the page's
        default from what the user entered on previous pages, this is the
        function to reimplement.
        """
        self.widget.update()


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


class StepWidget(QtGui.QWidget):

    """
    Page that allows setting an optic and then measuring the MONITOR.
    """

    # TODO: CanForward() -> BeamIsStable()

    def __init__(self, ovm, num_focus_levels=6):
        super(StepWidget, self).__init__()
        uic.loadUi(resource_filename(__name__, 'ovm_step.ui'), self)
        self.ovm = ovm
        focus_choices = ["Manual"]
        focus_choices += ["Focus {}".format(i+1)
                          for i in range(num_focus_levels)]
        self.focus_choice.addItems(focus_choices)
        self.focus_choice.currentIndexChanged.connect(self.on_change_focus)
        self.focus_choice.setCurrentIndex(0)
        self.exec_button.clicked.connect(self.on_exec)
        self._update_static_text()
        # PyQt4 fails to use the correct alignment from the .ui file:
        self.exec_layout.setAlignment(self.line_above, Qt.AlignHCenter)
        self.exec_layout.setAlignment(self.line_below, Qt.AlignHCenter)
        # load initial values:
        self._load_csys_qp_value(0, self.input_qp1_value)
        self._load_csys_qp_value(1, self.input_qp2_value)
        self.input_qp1_value.setValidator(QtGui.QDoubleValidator())
        self.input_qp2_value.setValidator(QtGui.QDoubleValidator())

    def _update_static_text(self):
        qp1 = self.ovm.get_qp(0)
        qp2 = self.ovm.get_qp(1)
        self._update_qp_labels(qp1, self.input_qp1_label, self.input_qp1_unit)
        self._update_qp_labels(qp1, self.displ_qp1_label, self.displ_qp1_unit)
        self._update_qp_labels(qp2, self.input_qp2_label, self.input_qp2_unit)
        self._update_qp_labels(qp2, self.displ_qp2_label, self.displ_qp2_unit)

    def _update_qp_labels(self, qp_elem, label, unit):
        param_info = qp_elem.dvm_converter.param_info['kL']
        set_text(label, param_info.name + ':')
        set_text(unit, get_raw_label(param_info.ui_unit))

    def on_change_focus(self, focus):
        """Update focus level and automatically load QP values."""
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

    def on_exec(self):
        """Write QP values to the control system."""
        self._write_qp_value(0, self.input_qp1_value)
        self._write_qp_value(1, self.input_qp2_value)
        self.ovm.control._plugin.execute()

    def _write_qp_value(self, index, ctrl):
        """Transmit the value of a single QP to the control system."""
        qp_elem = self.ovm.get_qp(index)
        param_info = qp_elem.dvm_converter.param_info['kL']
        qp_value = float(ctrl.text())
        qp_value = qp_value * param_info.ui_unit
        values = {'kL': qp_value}
        qp_elem.mad_backend.set(qp_elem.mad_converter.to_backend(values))
        qp_elem.dvm_backend.set(qp_elem.dvm_converter.to_backend(values))

    def update_ui(self):
        # update monitor data
        data = self.ovm.get_monitor().dvm_backend.get()
        set_text(self.monitor_x_value, '{:5}'.format(data['posx'].magnitude))
        set_text(self.monitor_y_value, '{:5}'.format(data['posy'].magnitude))
        set_text(self.monitor_x_unit, get_raw_label(data['posx']))
        set_text(self.monitor_y_unit, get_raw_label(data['posy']))
        # update qps
        self._load_csys_qp_value(0, self.displ_qp1_value)
        self._load_csys_qp_value(1, self.displ_qp2_value)

    def _load_csys_qp_value(self, index, ctrl):
        """Get QP value from control system."""
        qp_elem = self.ovm.get_qp(index)
        param_info = qp_elem.dvm_converter.param_info['kL']
        data = qp_elem.dvm_backend.get()
        text = '{:5}'.format(strip_unit(data['kL'], param_info.ui_unit))
        set_text(ctrl, text)


class ParameterInfo(object):

    def __init__(self, param, value):
        self.name = param
        self.value = value


class SummaryWidget(QtGui.QWidget):

    """
    Final summary + confirm page for the OVM wizard. Shows calculated initial
    position and steerer corrections.
    """

    steerer_cols = twiss_cols = [
        ColumnInfo("Param", 'name'),
        ColumnInfo("Value", 'value'),
    ]

    # TODO: dynamically enable update/calculate buttons

    def __init__(self, ovm):
        super(SummaryWidget, self).__init__()
        uic.loadUi(resource_filename(__name__, 'ovm_summary.ui'), self)
        self.update_button.clicked.connect(self.update)
        self.execute_button.clicked.connect(self.execute)
        self.ovm = ovm
        self.beaminit_table.set_columns(self.twiss_cols)
        self.corrections_table.set_columns(self.steerer_cols)
        self.x_target_check.toggled.connect(self.on_check)
        self.y_target_check.toggled.connect(self.on_check)
        self.x_target_value.setValidator(QtGui.QDoubleValidator())
        self.y_target_value.setValidator(QtGui.QDoubleValidator())

        # TODO: add a restart button

    def on_check(self):
        enable = (self.x_target_check.isChecked() or
                  self.y_target_check.isChecked())
        self.update_button.setEnabled(enable)

    def update(self):
        """Calculate initial positions / corrections."""
        data = self.ovm.measurement[0]
        set_text(self.x_target_unit, get_raw_label(data['posx']))
        set_text(self.y_target_unit, get_raw_label(data['posy']))
        pos = self.ovm.compute_initial_position()
        xpos = float(self.x_target_value.text()) if self.x_target_check.isChecked() else None
        ypos = float(self.y_target_value.text()) if self.y_target_check.isChecked() else None
        self.steerer_corrections = self.ovm.compute_steerer_corrections(pos, xpos, ypos)
        steerer_corrections_rows = [
            ParameterInfo(el.dvm_params[k].name, v)
            for el, vals in self.steerer_corrections
            for k, v in el.mad2dvm(vals).items()
        ]
        beaminit_rows = [
            ParameterInfo(name, value)
            for name, value in pos.items()
        ]
        self.beaminit_table.rows = sorted(beaminit_rows,
                                          key=lambda item: item.name)
        self.corrections_table.rows = steerer_corrections_rows

    def execute(self):
        """Apply calculated corrections."""
        for el, vals in self.steerer_corrections:
            el.mad_backend.set(vals)
            el.dvm_backend.set(el.mad2dvm(vals))
        self.ovm.control._plugin.execute()
        self.ovm.segment.retrack()
