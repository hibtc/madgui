# encoding: utf-8
"""
Multi grid correction method.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from pkg_resources import resource_filename

import numpy as np

from madqt.qt import QtCore, QtGui, uic
from madqt.core.unit import get_unit, allclose
from madqt.widget.tableview import ColumnInfo
from madqt.util.collections import List

from .correct_base import (
    OrbitCorrectorBase,
    CorrectorWidgetBase,
    _is_steerer,
    display_name,
    el_names,
    set_text,
)

from .optic_variation import (
    SelectWidget as OVM_SelectWidget,
)


# TODO:
# - allow more than 2 monitors
# - use CORRECT command from MAD-X rather than custom numpy method?
# - combine with optic variation method


class Corrector(OrbitCorrectorBase):

    """
    Single target orbit correction via optic variation.
    """

    def __init__(self, control, target, monitors, x_steerers, y_steerers):
        super(Corrector, self).__init__(
            control,
            targets=[target],
            magnets=[],
            monitors=monitors,
            x_steerers=x_steerers,
            y_steerers=y_steerers)
        self.target = target


class SelectWidget(OVM_SelectWidget):

    """
    Select elements for "optik-varianz" method.
    """

    def __init__(self, *args, **kwargs):
        super(SelectWidget, self).__init__(*args, **kwargs)
        self.label_monitor.setText("Target:")
        self.label_qp1.setText("Monitor 1:")
        self.label_qp2.setText("Monitor 2:")

    def set_elements(self, elements, config):
        """Set valid elements and default choices."""
        self.config = config if config else {}
        self.elements = elements
        self.elem_mon = [el for el in elements if el['type'].endswith('monitor')]
        self.elem_tgt = self.elem_mon
        self.elem_dip = [el for el in elements if _is_steerer(el)]
        self.choice_monitor.addItems(el_names(self.elem_tgt))
        for ctrl in self.ctrl_qps:
            ctrl.addItems(el_names(self.elem_mon))
        for ctrl in self.ctrl_hst + self.ctrl_vst:
            ctrl.addItems(el_names(self.elem_dip))
        if config:
            sel = max(self.choice_monitor.findText(display_name(tgt))
                      for tgt in config)
        else:
            sel = len(self.elem_mon) - 1
        self.choice_monitor.setCurrentIndex(sel)

    def on_change_monitor(self):
        """Update QP/steerer choices when selecting a configured monitor."""
        conf = self.config.get(self.choice_monitor.currentText().upper(), {})
        elem_ctrls = (self.ctrl_qps, self.ctrl_hst, self.ctrl_vst)
        conf_sects = ('monitor', 'x_steerer', 'y_steerer')
        # handle sections individually to allow partial config:
        for ctrls, sect in zip(elem_ctrls, conf_sects):
            for ctrl, name in zip(ctrls, conf.get(sect, ())):
                ctrl.setCurrentIndex(ctrl.findText(display_name(name)))



class CorrectorWidget(CorrectorWidgetBase):

    ui_file = 'mgm_dialog.ui'

    def init_controls(self):
        # input group
        self.mon1_title.setText(display_name(self.corrector.monitors[0]))
        self.mon2_title.setText(display_name(self.corrector.monitors[1]))
        self.target_title.setText("Design value at target {}"
                                  .format(display_name(self.corrector.target)))

        orbit = self.corrector.get_dvm(self.corrector.monitors[0])
        self.x_target_value.unit = get_unit(orbit['posx'])
        self.y_target_value.unit = get_unit(orbit['posy'])
        # result groups
        self.twiss_table.set_columns(self.twiss_columns)
        self.corrections_table.set_columns(self.steerer_columns)
        self.twiss_table.horizontalHeader().hide()

    def set_initial_values(self):
        self.x_target_value.value = 0
        self.y_target_value.value = 0
        self.update_fit_button.setFocus()
        self.update_csys_values()
        # update table views
        self.update_fit()
        self.update_corrections()

    def connect_signals(self):
        self.update_csys_values_timer = QtCore.QTimer()
        self.update_csys_values_timer.timeout.connect(self.update_csys_values)
        self.update_csys_values_timer.start(100)

        # connect signals
        # …perform action upon explicit user request
        self.update_fit_button.clicked.connect(self.update_fit)
        self.execute_corrections.clicked.connect(self.on_execute_corrections)

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

        # NOTE: self.update_corrections() is called in update_fit(), so we
        # don't need to connect something like twiss_table.valueChanged.

    def update_csys_values(self):
        self._load_csys_mon_value(0, self.mon1_x_value, self.mon1_y_value)
        self._load_csys_mon_value(1, self.mon2_x_value, self.mon2_y_value)

    def _load_csys_mon_value(self, index, ctrl_x, ctrl_y):
        elem = self.corrector.monitors[index]
        data = self.corrector.get_dvm(elem)
        ctrl_x.quantity = data['posx']
        ctrl_y.quantity = data['posy']

    def update_fit(self):
        self.corrector.clear_orbit_records()
        self.corrector.add_orbit_records(
            self.corrector.current_orbit_records())
        super(CorrectorWidget, self).update_fit()
