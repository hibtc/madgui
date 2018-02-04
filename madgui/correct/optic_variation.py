"""
Utilities for the optic variation method (Optikvarianzmethode) for beam
alignment.
"""

from pkg_resources import resource_filename

from madgui.qt import Qt, QtCore, QtGui, uic
from madgui.core.unit import get_unit, allclose, tounit
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
        self.utool = control._model.utool
        self.model = control._model
        knobs = control.get_knobs()
        self._optics = {dknob.param: (mknob, dknob) for mknob, dknob in knobs}
        self._knobs = {mknob.el_name: (mknob, dknob) for mknob, dknob in knobs}
        # save elements
        self.targets = targets
        self.magnets = magnets
        self.monitors = monitors
        self.x_steerers = x_steerers
        self.y_steerers = y_steerers
        # recorded transfer maps + monitor measurements
        self.orbit_records = List()
        control._frame.open_graph('orbit')

    started = False

    def start(self):
        if not self.started:
            self.started = True
            self.backup()

    def stop(self):
        if self.started:
            self.started = False
            self.restore()

    # access element values

    def get_info(self, elem):
        mknob, dknob = self._knobs[elem]
        return dknob.info

    def get_dvm(self, elem):
        mknob, dknob = self._knobs[elem]
        return dknob.read()

    def set_dvm(self, elem, data):
        mknob, dknob = self._knobs[elem]
        dknob.write(data)

    def get_transfer_map(self, dest, orig=None, optics=(), init_orbit=None):
        self.apply_mad_optics(optics)
        # TODO: get multiple transfer maps in one TWISS call

        # update initial conditions to compute sectormaps accounting for the
        # given initial conditions:
        twiss_args_backup = self.model.twiss_args.copy()
        if init_orbit:
            init_twiss = self.model.twiss_args.copy()
            init_twiss.update(init_orbit)
            self.model.twiss_args = init_twiss

        try:
            return self.model.get_transfer_maps([
                self.model.start if orig is None else orig,
                self.model.get_element_info(dest)])[1]
        finally:
            self.model.twiss_args = twiss_args_backup

    def sync_csys_to_mad(self):
        """Update element settings in MAD-X from control system."""
        self.control.read_all()
        self.model.twiss_args = self.backup_twiss_args

    def get_csys_optics(self):
        return [(knob.param, knob.read())
                for _, knob in self._knobs.values()]

    def apply_mad_optics(self, optics):
        knobs = self._optics
        self.control.read_these([
            (mknob, None, dknob, val)
            for param, val in optics
            for mknob, dknob in [knobs[param]]
        ])

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
        return self.utool.dict_add_unit({
            'x': x, 'px': px,
            'y': y, 'py': py,
        }), chi_squared, singular

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
        steerer_knobs = [self._knobs[elem] for elem in steerer_names]

        # construct initial conditions
        init_twiss = {}
        init_twiss.update(self.model.twiss_args)
        init_twiss.update(init_orbit)
        self.model.twiss_args = init_twiss

        # match final conditions
        match_names = [mknob.param for mknob, _ in steerer_knobs]
        constraints = [
            dict(range=target, **self.utool.dict_strip_unit(orbit))
            for target, orbit in zip(self.targets, design_orbit)
        ]
        self.model.madx.match(
            sequence=self.model.sequence.name,
            vary=match_names,
            weight={'x': 1e3, 'y':1e3, 'px':1e3, 'py':1e3},
            constraints=constraints,
            twiss_init=self.utool.dict_strip_unit(init_twiss))
        self.model.twiss.invalidate()

        # return corrections
        return [(mknob, mknob.read(), dknob, dknob.read())
                for mknob, dknob in steerer_knobs]

    def backup(self):
        self.backup_twiss_args = self.model.twiss_args
        self.backup_strengths = [
            (mknob, mknob.read())
            for mknob, _ in self._knobs.values()
        ]

    def restore(self):
        for mknob, value in self.backup_strengths:
            mknob.write(value)
        self.model.twiss_args = self.backup_twiss_args

    def _strip_sd_pair(self, sd_values, prefix='pos'):
        strip_unit = self.utool.strip_unit
        return (strip_unit('x', sd_values[prefix + 'x']),
                strip_unit('y', sd_values[prefix + 'y']))


def _is_steerer(el):
    return el.Type == 'sbend' \
        or el.Type.endswith('kicker') \
        or el.Type == 'multipole' and (
            el.Knl[0] != 0 or
            el.Ksl[0] != 0)


def display_name(name):
    return name.upper()


def el_names(elems):
    return [display_name(el.Name) for el in elems]


def set_text(ctrl, text):
    """Update text in a control, but avoid flicker/deselection."""
    if ctrl.text() != text:
        ctrl.setText(text)


def get_kL(index):
    return lambda record: record.gui_optics[index]


class CorrectorWidget(QtGui.QWidget):

    initial_particle_orbit = None
    steerer_corrections = None

    ui_file = 'ovm_dialog.ui'

    records_columns = [
        ColumnInfo("QP1", get_kL(0), resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("QP2", get_kL(1)),
        ColumnInfo("x", 'x'),
        ColumnInfo("y", 'y'),
    ]

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
        self.shown = True
        self.update_csys_values_timer = QtCore.QTimer()
        self.update_csys_values_timer.timeout.connect(self.update_csys_values)
        self.update_csys_values_timer.start(1000)

    def hideEvent(self, event):
        if self.shown:
            self.shown = False
            self.update_csys_values_timer.timeout.disconnect(self.update_csys_values)
            self.update_csys_values_timer.stop()

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
            ParameterInfo(dknob.param, mknob.to(dknob.attr, mval), dval)
            for mknob, mval, dknob, dval in self.steerer_corrections
        ]
        self.corrections_table.rows = steerer_corrections_rows
        self.corrections_table.resizeColumnToContents(0)

        # TODO: make 'optimal'-column in corrections_table editable and update
        #       self.execute_corrections.setEnabled according to its values

    def on_execute_corrections(self):
        """Apply calculated corrections."""
        self.corrector.restore()
        for mknob, mval, dknob, dval in self.steerer_corrections:
            mknob.write(mval)
            dknob.write(mknob.to(dknob.attr, mval))
        self.corrector.backup()
        self.corrector.control._plugin.execute()
        self.corrector.model.twiss.invalidate()
        self.corrector.clear_orbit_records()

    num_focus_levels = 6
    update_record_index = None

    def init_controls(self):
        # input group
        focus_choices = ["Focus {}".format(i+1)
                         for i in range(self.num_focus_levels)]
        self.focus_choice.addItems(focus_choices)
        self.focus_choice.setCurrentIndex(0)
        par1 = self.corrector.get_info(self.corrector.magnets[0])
        par2 = self.corrector.get_info(self.corrector.magnets[1])
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
        self.records_table.horizontalHeader().setHighlightSections(False)
        self.fit_table.horizontalHeader().hide()

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
            not allclose(input_optics, displ_optics))

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
            if allclose(optics, current_optics))
        self.update_record_index = next(same_values, None)
        self.qp_settings_record.setEnabled(self.update_record_index is None)
        self.records_table.clearSelection()
        if self.update_record_index is not None:
            self.records_table.selectRow(self.update_record_index)
        # new_text = "Record" if self.update_record_index is None else "Update"
        # set_text(self.qp_settings_record, new_text)


class SelectWidget(QtGui.QWidget):

    """
    Select elements for "optik-varianz" method.
    """

    def __init__(self, elements, config):
        super().__init__()
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
        self.elem_mon = [el for el in elements if el.Type.endswith('monitor')]
        self.elem_qps = [el for el in elements if el.Type == 'quadrupole']
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
            return elems[sel].At
        try:
            at_mon = _at(sel_mon, self.elem_mon)
            at_qp = [_at(sel, self.elem_qps) for sel in sel_qp]
            at_st = [_at(sel, self.elem_dip) for sel in sel_st]
        except ValueError:
            return False
        return all(at <= at_mon for at in at_qp + at_st)
