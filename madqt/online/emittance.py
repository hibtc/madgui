# encoding: utf-8
"""
UI for matching.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from pkg_resources import resource_filename
from collections import namedtuple

from madqt.qt import QtGui, uic
from madqt.widget.tableview import ColumnInfo, ExtColumnInfo

import madqt.online.elements as elements
from madqt.util.collections import List
from madqt.util.enum import make_enum


MonitorItem = namedtuple('MonitorItem', ['proxy', 'envx', 'envy'])
ResultItem = namedtuple('ResultItem', ['name', 'measured', 'model'])


def get_monitor_elem(widget, m):
    return widget.monitor_enum(m.proxy.name)

def set_monitor_elem(widget, m, i, name):
    if name is not None:
        p = widget.monitor_map[str(name)]
        v = p.dvm_backend.get()
        widget.monitors[i] = MonitorItem(p, v.get('widthx'), v.get('widthy'))


class EmittanceWidget(QtGui.QWidget):

    ui_file = 'emittance.ui'

    monitor_columns = [
        ExtColumnInfo("Monitor", get_monitor_elem, set_monitor_elem),
        ExtColumnInfo("Δx", 'envx'),
        ExtColumnInfo("Δy", 'envy'),
    ]

    result_columns = [
        ColumnInfo("Name", 'name'),
        ColumnInfo("Measured", 'measured'),
        ColumnInfo("Model", 'model'),
    ]

    def __init__(self, control):
        super(EmittanceWidget, self).__init__()
        uic.loadUi(resource_filename(__name__, self.ui_file), self)
        self.control = control

        monitors = list(control.iter_elements(elements.Monitor))
        self.monitor_map = {m.name: m for m in monitors}
        self.monitor_enum = make_enum('Monitor', [m.name for m in monitors])
        self.monitors = List()
        self.results = List()

        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    # The three steps of UI initialization

    def init_controls(self):
        self.mtab.horizontalHeader().setHighlightSections(False)
        self.rtab.horizontalHeader().setHighlightSections(False)
        self.mtab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.rtab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.mtab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.rtab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.mtab.set_columns(self.monitor_columns, self.monitors, self)
        self.rtab.set_columns(self.result_columns, self.results, self)

    def set_initial_values(self):
        pass

    def connect_signals(self):
        # update UI
        self.mtab.selectionChangedSignal.connect(self.selection_changed_monitor)
        self.monitors.update_after.connect(self.on_monitor_changed)
        # TODO: update UI: ok/export buttons
        # monitor actions
        self.button_remove_monitor.clicked.connect(self.mtab.removeSelectedRows)
        self.button_clear_monitor.clicked.connect(self.monitors.clear)
        self.button_add_monitor.clicked.connect(self.add_monitor)
        self.button_update_monitor.clicked.connect(self.update_monitor)
        # result actions
        self.button_ok.clicked.connect(self.accept)
        self.button_cancel.clicked.connect(self.reject)
        self.button_export.clicked.connect(self.export)

    def selection_changed_monitor(self):
        self.button_remove_monitor.setEnabled(bool(self.mtab.selectedIndexes()))

    def on_monitor_changed(self):
        self.button_clear_monitor.setEnabled(bool(self.monitors))
        self.button_update_monitor.setEnabled(bool(self.monitors))
        self.match_values()

    def accept(self):
        # TODO: use values
        self.window().accept()

    def reject(self):
        self.window().reject()

    def export(self):
        pass

    def add_monitor(self):
        name = self.monitor_enum._values[0]
        prox = self.monitor_map[name]
        vals = prox.dvm_backend.get()
        self.monitors.append(MonitorItem(
            prox, vals.get('widthx'), vals.get('widthy')))

    def update_monitor(self):
        # reload values for all the monitors
        self.monitors[:] = [
            MonitorItem(m.proxy, v.get('widthx'), v.get('widthy'))
            for m in self.monitors
            for v in [m.proxy.dvm_backend.get()]
        ]

    def match_values(self):

        if len(self.monitors) < 3:
            self.results[:] = []
            return

        seg = self.control._segment
        madx = seg.madx
        cmd = madx.command

        beam = seg.sequence.beam
        twiss_args = seg.utool.dict_strip_unit(seg.twiss_args)

        # setup initial values
        madx.set_value('betx_emit_mm', twiss_args.get('betx'))
        madx.set_value('bety_emit_mm', twiss_args.get('bety'))
        madx.set_value('alfx_emit_mm', twiss_args.get('alfx'))
        madx.set_value('alfy_emit_mm', twiss_args.get('alfy'))
        madx.set_value('ex_emit_mm',   beam['ex'])
        madx.set_value('ey_emit_mm',   beam['ey'])

        # start matching block
        cmd.match('use_macro')

        cmd.vary(name='betx_emit_mm', lower=0)
        cmd.vary(name='bety_emit_mm', lower=0)
        cmd.vary(name='alfx_emit_mm')
        cmd.vary(name='alfy_emit_mm')
        cmd.vary(name='ex_emit_mm', lower=0)
        cmd.vary(name='ey_emit_mm', lower=0)

        madx.input('m1: macro = {{'
                   ' beam, sequence={}, ex=ex_emit_mm, ey=ey_emit_mm;'
                   ' twiss, betx=betx_emit_mm, alfx=alfx_emit_mm, '
                   '        bety=bety_emit_mm, alfy=alfy_emit_mm;'
                   '}};'.format(seg.sequence.name))

        for m in self.monitors:
            expr = 'expr= table(twiss,{},{})={}'.format
            strip = lambda q: seg.utool.strip_unit('envx', q)
            cmd.constraint('weight=1e5', expr(m.proxy.name, 'sig11', strip(m.envx)))
            cmd.constraint('weight=1e5', expr(m.proxy.name, 'sig33', strip(m.envy)))

        cmd.lmdif()
        cmd.endmatch()

        vars = madx.globals

        self.results[:] = [
            ResultItem('betx', vars['betx_emit_mm'], twiss_args.get('betx')),
            ResultItem('bety', vars['bety_emit_mm'], twiss_args.get('bety')),
            ResultItem('alfx', vars['alfx_emit_mm'], twiss_args.get('alfx')),
            ResultItem('alfy', vars['alfy_emit_mm'], twiss_args.get('alfy')),
            ResultItem('ex',   vars['ex_emit_mm'],   beam['ex']),
            ResultItem('ey',   vars['ey_emit_mm'],   beam['ey']),
        ]
