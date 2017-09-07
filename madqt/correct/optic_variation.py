# encoding: utf-8
"""
Utilities for the optic variation method (Optikvarianzmethode) for beam
alignment.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from pkg_resources import resource_filename

from madqt.qt import Qt, QtCore, QtGui, uic
from madqt.core.unit import get_unit, allclose
from madqt.widget.tableview import ColumnInfo
from madqt.util.qt import notifyEvent

from ._base import (
    OrbitCorrectorBase,
    CorrectorWidgetBase,
    _is_steerer,
    display_name,
    el_names,
    set_text,
)


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


class Corrector(OrbitCorrectorBase):

    """
    Single target orbit correction via optic variation.
    """

    def __init__(self, control, target, quadrupoles, x_steerers, y_steerers):
        super(Corrector, self).__init__(
            control,
            targets=[target],
            magnets=quadrupoles,
            monitors=[target],
            x_steerers=x_steerers,
            y_steerers=y_steerers)
        self.target = target


class SelectWidget(QtGui.QWidget):

    """
    Select elements for "optik-varianz" method.
    """

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
            return elems[sel]['at']
        try:
            at_mon = _at(sel_mon, self.elem_mon)
            at_qp = [_at(sel, self.elem_qps) for sel in sel_qp]
            at_st = [_at(sel, self.elem_dip) for sel in sel_st]
        except ValueError:
            return False
        return all(at <= at_mon for at in at_qp + at_st)


def get_kL(index):
    def getter(record):
        return record.gui_optics[index]['kL']
    return getter


class CorrectorWidget(CorrectorWidgetBase):

    ui_file = 'ovm_dialog.ui'

    records_columns = [
        ColumnInfo("QP1", get_kL(0), resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("QP2", get_kL(1)),
        ColumnInfo("x", 'x'),
        ColumnInfo("y", 'y'),
    ]

    num_focus_levels = 6
    update_record_index = None

    def init_controls(self):
        # input group
        focus_choices = ["Focus {}".format(i+1)
                         for i in range(self.num_focus_levels)]
        self.focus_choice.addItems(focus_choices)
        self.focus_choice.setCurrentIndex(0)
        par1 = self.corrector.get_info(self.corrector.magnets[0])['kL']
        par2 = self.corrector.get_info(self.corrector.magnets[1])['kL']
        self.input_qp1_label.setText(par1.name + ':')
        self.input_qp2_label.setText(par2.name + ':')
        self.input_qp1_value.unit = par1.ui_unit
        self.input_qp2_value.unit = par2.ui_unit
        self.displ_qp1_value.unit = par1.ui_unit
        self.displ_qp2_value.unit = par2.ui_unit
        beam = self.corrector.get_dvm(self.corrector.target)
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
        self.update_csys_values_timer = QtCore.QTimer()
        self.update_csys_values_timer.timeout.connect(self.update_csys_values)
        self.update_csys_values_timer.start(100)

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

        self.fit_iterations_spinbox.valueChanged.connect(
            self.set_fit_iterations)

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

    def closeEvent(self, event):
        self.update_csys_values_timer.timeout.disconnect(self.update_csys_values)
        self.update_csys_values_timer.stop()

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
            {'kL': self.input_qp1_value.quantity})
        self.corrector.set_dvm(
            self.corrector.magnets[1],
            {'kL': self.input_qp2_value.quantity})
        self.corrector.control._plugin.execute()

    def update_csys_values(self):
        # update monitor data
        orbit = self.corrector.get_dvm(self.corrector.target)
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
        ctrl.set_quantity_checked(data['kL'])

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
        kL_values = [[optic['kL']
                      for optic in record.gui_optics]
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

    def set_fit_iterations(self, num):
        self.fit_iterations = num
        self.update_fit()
