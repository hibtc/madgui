"""
Utilities for the optic variation method (Optikvarianzmethode) for beam
alignment.
"""

import numpy as np

from madgui.qt import Qt, QtGui, load_ui
from madgui.core.unit import get_unit, tounit, ui_units
from madgui.widget.tableview import ColumnInfo
from madgui.util.collections import List
from madgui.util.qt import notifyEvent
from madgui.correct.orbit import fit_initial_orbit


# TODO:
# - update current steerer values regularly (+after execution)
# - automatically plot "orbit" and using initial_particle_orbit
# - use UI units
# - allow to select target (in beam group)?
# - prettier E notation (only for display)
# - let user specify target angle

__all__ = [
    'SelectWidget',
    'Corrector',
    'CorrectorWidget',
]

class OrbitRecord:

    def __init__(self, monitor, orbit, csys_optics, gui_optics):
        self.monitor = monitor
        self.orbit = orbit
        self.csys_optics = csys_optics
        self.gui_optics = gui_optics

    @property
    def x(self):
        return self.orbit['posx']

    @property
    def y(self):
        return self.orbit['posy']


class ParameterInfo:

    def __init__(self, param, value, current=None):
        self.name = param
        self.value = value
        self.current = current


class Corrector:

    """
    Single target orbit correction via optic variation.
    """

    def __init__(self, control, target, quadrupoles, x_steerers, y_steerers):
        targets = [target]
        magnets = quadrupoles
        monitors = [target]
        self.target = target
        self.control = control
        self.model = control.model()
        self._knobs = {knob.name.lower(): knob for knob in control.get_knobs()}
        # save elements
        self.targets = targets
        self.magnets = magnets
        self.monitors = monitors
        self.x_steerers = x_steerers
        self.y_steerers = y_steerers
        # recorded transfer maps + monitor measurements
        self.orbit_records = List()
        control._frame.open_graph('orbit')

    # access element values

    def get_dvm(self, knob):
        return self.control._plugin.read_param(knob)

    def set_dvm(self, knob, value):
        self.control._plugin.write_param(knob, value)

    def get_transfer_map(self, dest, orig=None, optics=(), init_orbit=None):
        self.model.write_params(optics)
        self.control.write_params(optics)
        # TODO: get multiple transfer maps in one TWISS call

        # update initial conditions to compute sectormaps accounting for the
        # given initial conditions:
        model = self.model
        with model.undo_stack.rollback("Orbit correction"):
            model.update_twiss_args(init_orbit or {})
            return model.sectormap(
                model.start if orig is None else orig,
                model.get_element_info(dest))

    def sync_csys_to_mad(self):
        """Update element settings in MAD-X from control system."""
        self.control.read_all()

    def get_csys_optics(self):
        return {knob: self.control._plugin.read_param(knob)
                for knob in self._knobs}

    # record monitor/model

    def current_orbit_records(self):
        csys_optics = self.get_csys_optics()
        magnet_optics = [self.get_dvm(magnet)
                         for magnet in self.magnets]
        return [
            OrbitRecord(
                monitor,
                self.control.read_monitor(monitor),
                csys_optics,
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

    def fit_particle_orbit(self, records=None, init_orbit=None):
        # TODO: add thresholds / abort conditions for bad initial conditions
        # TODO: save initial optics
        if records is None:
            records = self.orbit_records
        sectormaps = [
            self.get_transfer_map(record.monitor,
                                  optics=record.csys_optics,
                                  init_orbit=init_orbit)
            for record in records
        ]
        self.fit_results = fit_initial_orbit(*[
            (sectormap[:,:6], sectormap[:,6],
             self._strip_sd_pair(record.orbit))
            for record, sectormap in zip(records, sectormaps)
        ])
        initial_orbit, chi_squared, singular = self.fit_results
        x, px, y, py = initial_orbit
        return {
            'x': x, 'px': px,
            'y': y, 'py': py,
        }, chi_squared, singular

    def compute_steerer_corrections(self, init_orbit, design_orbit,
                                    correct_x=None, correct_y=None,
                                    targets=None):

        """
        Compute corrections for the x_steerers, y_steerers.

        :param dict init_orbit: initial conditions as returned by the fit
        :param list design_orbit: design orbit at the target positions
        """

        # TODO: make this work with backends other than MAD-X…

        if targets is None:
            targets = self.targets

        if correct_x is None:
            correct_x = any(('x' in orbit or 'px' in orbit)
                            for orbit in design_orbit)
        if correct_y is None:
            correct_y = any(('y' in orbit or 'py' in orbit)
                            for orbit in design_orbit)

        steerer_names = []
        if correct_x: steerer_names.extend(self.x_steerers)
        if correct_y: steerer_names.extend(self.y_steerers)

        def offset(elem, axis):
            dx, dy = self._monitor_offs.get(elem.name.lower(), (0, 0))
            if axis in ('x', 'posx'): return dx
            if axis in ('y', 'posy'): return dy
            return 0

        # match final conditions
        model = self.model
        match_names = steerer_names
        constraints = [
            (elem, None, axis, value+offset(elem, axis))
            for target, orbit in zip(self.targets, design_orbit)
            for elem in [model.elements[target]]
            for axis, value in orbit.items()
        ]
        with model.undo_stack.rollback("Orbit correction"):
            model.update_twiss_args(init_orbit)
            return model.match(
                vary=match_names,
                weight={'x': 1e3, 'y':1e3, 'px':1e3, 'py':1e3},
                constraints=constraints)

    def _strip_sd_pair(self, sd_values, prefix='pos'):
        return ('x', sd_values[prefix + 'x'],
                'y', sd_values[prefix + 'y'])


def _is_steerer(el):
    return el.base_name == 'sbend' \
        or el.base_name.endswith('kicker') \
        or el.base_name == 'multipole' and (
            el.Knl[0] != 0 or
            el.Ksl[0] != 0)


def display_name(name):
    return name.upper()


def el_names(elems):
    return [display_name(el.node_name) for el in elems]


def set_text(ctrl, text):
    """Update text in a control, but avoid flicker/deselection."""
    if ctrl.text() != text:
        ctrl.setText(text)


def get_kL(index):
    return lambda cell: cell.data.gui_optics[index]


class CorrectorWidget(QtGui.QWidget):

    initial_particle_orbit = None
    steerer_corrections = None

    ui_file = 'ovm_dialog.ui'

    records_columns = [
        ColumnInfo("QP1", get_kL(0), resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("QP2", get_kL(1)),
        ColumnInfo("x", 'x', convert=True),
        ColumnInfo("y", 'y', convert=True),
    ]

    # FIXME: units are broken in these two tabs:
    fit_columns = [
        ColumnInfo("Param", 'name'),
        ColumnInfo("Value", 'value', convert='name'),
        ColumnInfo("Unit", lambda c: ui_units.label(c.data.name),
                   resize=QtGui.QHeaderView.ResizeToContents),
    ]

    steerer_columns = [
        ColumnInfo("Steerer", 'name'),
        ColumnInfo("Optimal", 'value', convert='name'),
        ColumnInfo("Current", 'current', convert='name'),
        ColumnInfo("Unit", lambda c: ui_units.label(c.data.name),
                   resize=QtGui.QHeaderView.ResizeToContents),
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

    def update_records(self):
        self.records_table.rows = self.corrector.orbit_records

    def update_fit(self):
        """Calculate initial positions / corrections."""
        if len(self.corrector.orbit_records) < 2:
            self._update_fit_table(None, [])
            return
        self.corrector.sync_csys_to_mad()
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
            ParameterInfo(knob, value, self.corrector.get_dvm(knob))
            for knob, value in self.steerer_corrections.items()
        ]
        self.corrections_table.rows = steerer_corrections_rows
        self.corrections_table.resizeColumnToContents(0)

        # TODO: make 'optimal'-column in corrections_table editable and update
        #       self.execute_corrections.setEnabled according to its values

    def on_execute_corrections(self):
        """Apply calculated corrections."""
        self.corrector.model.write_params(self.steerer_corrections.items())
        self.corrector.control.write_params(self.steerer_corrections.items())
        self.corrector.apply()
        self.corrector.control._plugin.execute()
        self.corrector.clear_orbit_records()

    num_focus_levels = 6
    update_record_index = None

    def init_controls(self):
        # input group
        focus_choices = ["Focus {}".format(i+1)
                         for i in range(self.num_focus_levels)]
        self.focus_choice.addItems(focus_choices)
        self.focus_choice.setCurrentIndex(0)
        par1 = self.corrector._knobs[self.corrector.magnets[0]]
        par2 = self.corrector._knobs[self.corrector.magnets[1]]
        self.input_qp1_label.setText(par1.name + ':')
        self.input_qp2_label.setText(par2.name + ':')
        self.input_qp1_value.unit = par1.ui_unit
        self.input_qp2_value.unit = par2.ui_unit
        self.displ_qp1_value.unit = par1.ui_unit
        self.displ_qp2_value.unit = par2.ui_unit
        beam = self.corrector.control.read_monitor(self.corrector.target)
        self.x_target_value.unit = get_unit(beam['posx'])
        self.y_target_value.unit = get_unit(beam['posx'])
        # result groups
        self.group_beam.setTitle("Beam at target {}"
                                 .format(display_name(self.corrector.target)))
        self.records_columns[0].title = par1.name
        self.records_columns[1].title = par2.name
        # TODO: also set target name in records_columns?
        self.records_table.set_columns(self.records_columns)
        self.fit_table.set_columns(self.fit_columns)
        self.corrections_table.set_columns(self.steerer_columns)
        self.records_table.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.records_table.header().setHighlightSections(False)
        self.fit_table.header().hide()

    def set_initial_values(self):
        self.x_target_value.value = 0
        self.y_target_value.value = 0
        self._load_csys_qp_value(0, self.input_qp1_value)
        self._load_csys_qp_value(1, self.input_qp2_value)
        self.input_qp1_value.selectAll()
        self.focus_choice.setCurrentIndex(3)
        self.update_csys_values()
        # update table views
        self.update_records()
        self.update_fit()
        # update button states
        self.update_clear_button()
        self.update_record_button()
        self.update_execute_button()

    def connect_signals(self):
        # connect signals
        # …perform action upon explicit user request
        self.load_preset_execute.clicked.connect(self.on_load_preset_execute)
        self.qp_settings_execute.clicked.connect(self.on_qp_settings_execute)
        self.qp_settings_record.clicked.connect(self.on_qp_settings_record)
        self.clear_records.clicked.connect(self.corrector.clear_orbit_records)
        self.execute_corrections.clicked.connect(self.on_execute_corrections)

        # …update records display
        self.corrector.orbit_records.mirror(self.records_table.rows)
        notifyEvent(self.records_table, 'keyPressEvent',
                    self._records_keyPressEvent)

        # …update steerer calculations when changing the target values:
        self.x_target_value.editingFinished.connect(self.update_corrections)
        self.y_target_value.editingFinished.connect(self.update_corrections)
        self.x_target_check.toggled.connect(self.update_corrections)
        self.y_target_check.toggled.connect(self.update_corrections)

        # …at least one target has to be on
        self.x_target_check.toggled.connect(
            lambda checked: checked or self.y_target_check.setChecked(True))
        self.y_target_check.toggled.connect(
            lambda checked: checked or self.x_target_check.setChecked(True))

        # …update beam initial conditions, when records have changed
        self.corrector.orbit_records.update_after.connect(
            lambda *args: self.update_fit())

        # NOTE: self.update_corrections() is called in update_fit(), so we
        # don't need to connect something like fit_table.valueChanged.

        # …update button states
        self.corrector.orbit_records.update_after.connect(self.update_clear_button)
        self.corrector.orbit_records.update_after.connect(self.update_record_button)
        self.displ_qp1_value.valueChanged.connect(self.update_record_button)
        self.displ_qp2_value.valueChanged.connect(self.update_record_button)
        self.displ_qp1_value.valueChanged.connect(self.update_execute_button)
        self.displ_qp2_value.valueChanged.connect(self.update_execute_button)
        self.input_qp1_value.valueChanged.connect(self.update_execute_button)
        self.input_qp2_value.valueChanged.connect(self.update_execute_button)
        # self.execute_corrections is updated in self.update_corrections()

    def _records_keyPressEvent(self, event):
        if self.records_table.state() == QtGui.QAbstractItemView.NoState:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                selection = self.records_table.selectedIndexes()
                if selection:
                    del self.corrector.orbit_records[selection[0].row()]

    def on_load_preset_execute(self):
        """Update focus level and automatically load QP values."""
        focus = self.focus_choice.currentIndex() + 1
        if focus == 0:
            return
        # TODO: this should be done with a more generic API
        # TODO: do this without beamoptikdll to decrease the waiting time
        dvm = self.corrector.control._plugin._dvm
        values, channels = dvm.GetMEFIValue()
        vacc = dvm.GetSelectedVAcc()
        if focus != channels.focus:
            dvm.SelectMEFI(vacc, *channels._replace(focus=focus))
        self._load_csys_qp_value(0, self.input_qp1_value)
        self._load_csys_qp_value(1, self.input_qp2_value)
        if focus != channels.focus:
            dvm.SelectMEFI(vacc, *channels)

    def on_qp_settings_record(self):
        self.corrector.add_orbit_records(
            self.corrector.current_orbit_records(),
            self.update_record_index)

    def on_qp_settings_execute(self):
        """Write QP values to the control system."""
        self.corrector.set_dvm(
            self.corrector.magnets[0],
            self.input_qp1_value.quantity)
        self.corrector.set_dvm(
            self.corrector.magnets[1],
            self.input_qp2_value.quantity)
        self.corrector.control._plugin.execute()

    def update_csys_values(self):
        # update monitor data
        orbit = self.corrector.control.read_monitor(self.corrector.target)
        self.x_monitor_value.quantity = orbit['posx']
        self.y_monitor_value.quantity = orbit['posy']
        # update qps
        self._load_csys_qp_value(0, self.displ_qp1_value)
        self._load_csys_qp_value(1, self.displ_qp2_value)
        return orbit

    def _load_csys_qp_value(self, index, ctrl):
        """Get QP value from control system."""
        magnet = self.corrector.magnets[index]
        data = self.corrector.get_dvm(magnet)
        ctrl.set_quantity_checked(data)

    def update_execute_button(self):
        input_optics = [self.input_qp1_value.quantity,
                        self.input_qp2_value.quantity]
        displ_optics = [self.displ_qp1_value.quantity,
                        self.displ_qp2_value.quantity]
        self.qp_settings_execute.setEnabled(
            not np.allclose(input_optics, displ_optics))

    def update_clear_button(self, *args):
        self.clear_records.setEnabled(
            bool(self.corrector.orbit_records))

    def update_record_button(self, *args):
        current_optics = [self.displ_qp1_value.quantity,
                          self.displ_qp2_value.quantity]
        kL_values = [record.gui_optics
                     for record in self.corrector.orbit_records]
        same_values = (
            idx for idx, optics in enumerate(kL_values)
            if np.allclose(optics, current_optics))
        self.update_record_index = next(same_values, None)
        self.qp_settings_record.setEnabled(self.update_record_index is None)
        self.records_table.clearSelection()
        #if self.update_record_index is not None:
        #    self.records_table.selectRow(self.update_record_index)
        # new_text = "Record" if self.update_record_index is None else "Update"
        # set_text(self.qp_settings_record, new_text)


class SelectWidget(QtGui.QWidget):

    """
    Select elements for "optik-varianz" method.
    """

    def __init__(self, elements, config):
        super().__init__()
        load_ui(self, __package__, 'ovm_select.ui')
        self.choice_monitor.currentIndexChanged.connect(self.on_change_monitor)
        self.ctrl_qps = (self.choice_qp1, self.choice_qp2)
        self.ctrl_hst = (self.choice_hsteer1, self.choice_hsteer2)
        self.ctrl_vst = (self.choice_vsteer1, self.choice_vsteer2)
        self.set_elements(elements, config)

    def set_elements(self, elements, config):
        """Set valid elements and default choices."""
        self.config = config if config else {}
        self.elements = elements
        self.elem_mon = [el for el in elements if el.base_name.endswith('monitor')]
        self.elem_qps = [el for el in elements if el.base_name == 'quadrupole']
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
        conf_sects = ('quadrupole', 'x_steerer', 'y_steerer')
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
            return elems[sel].position
        try:
            at_mon = _at(sel_mon, self.elem_mon)
            at_qp = [_at(sel, self.elem_qps) for sel in sel_qp]
            at_st = [_at(sel, self.elem_dip) for sel in sel_st]
        except ValueError:
            return False
        return all(at <= at_mon for at in at_qp + at_st)
