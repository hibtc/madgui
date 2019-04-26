"""
Plugin that integrates a beamoptikdll UI into MadGUI.
"""

__all__ = [
    'Control',
    'BeamSampler',
    'MonitorReadout',
]

import logging
from importlib import import_module
import time

import numpy as np
from PyQt5.QtCore import QTimer

from madgui.util.signal import Signal
from madgui.util.qt import SingleWindow
from madgui.util.collections import Bool, List

# TODO: catch exceptions and display error messages
# TODO: automate loading ACS parameters via model and/or named hook


class Control:

    """
    Plugin class for MadGUI.

    When connected, the plugin can be used to access parameters in the online
    database. This works only if the corresponding parameters were named
    exactly as in the database and are assigned with the ":=" operator.
    """

    def __init__(self, session):
        self.session = session
        self.backend = None
        self.model = session.model
        self.sampler = BeamSampler(self)
        # menu conditions
        self.is_connected = Bool(False)
        self.has_backend = Bool(False)
        self.can_connect = ~self.is_connected & self.has_backend
        self.has_sequence = self.is_connected & self.model
        self._config = config = session.config.online_control
        self._settings = config['settings']
        self._on_model_changed()
        self.set_backend(config.backend)

    def set_backend(self, qualname):
        self.backend_spec = qualname
        self.has_backend.set(bool(qualname))

    # menu handlers

    def connect(self):
        qualname = self.backend_spec
        logging.info('Connecting online control: {}'.format(qualname))
        modname, clsname = qualname.split(':')
        mod = import_module(modname)
        cls = getattr(mod, clsname)
        self.backend = cls(self.session, self._settings)
        self.backend.connect()
        self.session.user_ns.acs = self.backend
        self.is_connected.set(True)
        self.model.changed.connect(self._on_model_changed)
        self._on_model_changed()

    def disconnect(self):
        self._settings = self.export_settings()
        self.session.user_ns.acs = None
        self.backend.disconnect()
        self.backend = None
        self.is_connected.set(False)
        self.model.changed.disconnect(self._on_model_changed)
        self._on_model_changed()

    def _on_model_changed(self, model=None):
        model = model or self.model()
        elems = self.is_connected() and model and model.elements or ()
        self.sampler.monitors = [
            elem.name
            for elem in elems
            if elem.base_name.lower().endswith('monitor')
            or elem.base_name.lower() == 'instrument'
        ]

    def export_settings(self):
        if hasattr(self.backend, 'export_settings'):
            return self.backend.export_settings()
        return self._settings

    def get_knobs(self):
        """Get dict of lowercase name → :class:`ParamInfo`."""
        if not self.model():
            return {}
        return {
            knob: info
            for knob in self.model().export_globals()
            for info in [self.backend.param_info(knob)]
            if info
        }

    # TODO: unify export/import dialog -> "show knobs"
    # TODO: can we drop the read-all button in favor of automatic reads?
    # (SetNewValueCallback?)
    def on_read_all(self):
        """Read all parameters from the online database."""
        from madgui.online.dialogs import ImportParamWidget
        self._show_sync_dialog(ImportParamWidget(), self.read_all)

    def on_write_all(self):
        """Write all parameters to the online database."""
        from madgui.online.dialogs import ExportParamWidget
        self._show_sync_dialog(ExportParamWidget(), self.write_all)

    def _show_sync_dialog(self, widget, apply):
        from madgui.online.dialogs import SyncParamItem
        from madgui.widget.dialog import Dialog
        model, live = self.model(), self.backend
        widget.data = [
            SyncParamItem(info, live.read_param(name), model.read_param(name))
            for name, info in self.get_knobs().items()
        ]
        widget.data_key = 'acs_parameters'
        dialog = Dialog(self.session.window())
        dialog.setExportWidget(widget, self.session.folder)
        dialog.serious.updateButtons()
        dialog.accepted.connect(apply)
        dialog.show()
        return dialog

    def read_all(self, knobs=None):
        live = self.backend
        self.model().write_params([
            (knob, live.read_param(knob))
            for knob in knobs or self.get_knobs()
        ], "Read params from online control")

    def write_all(self, knobs=None):
        model = self.model()
        self.write_params([
            (knob, model.read_param(knob))
            for knob in knobs or self.get_knobs()
        ])

    def on_read_beam(self):
        # TODO: add confirmation dialog
        self.read_beam()

    def read_beam(self):
        self.model().update_beam(self.backend.get_beam())

    def read_monitor(self, name):
        return self.backend.read_monitor(name)

    @SingleWindow.factory
    def monitor_widget(self):
        """Read out SD values (beam position/envelope)."""
        from madgui.online.diagnostic import MonitorWidget
        return MonitorWidget(self.session)

    @SingleWindow.factory
    def orm_measure_widget(self):
        """Measure ORM for later analysis."""
        from madgui.widget.dialog import Dialog
        from madgui.online.orm_measure import MeasureWidget
        widget = MeasureWidget(self.session)
        return Dialog(self.session.window(), widget)

    def on_correct_multi_grid_method(self):
        from madgui.widget.correct.multi_grid import CorrectorWidget
        from madgui.widget.dialog import Dialog
        self.read_all()
        widget = CorrectorWidget(self.session)
        return Dialog(self.session.window(), widget)

    def on_correct_optic_variation_method(self):
        from madgui.widget.correct.optic_variation import CorrectorWidget
        from madgui.widget.dialog import Dialog
        self.read_all()
        widget = CorrectorWidget(self.session)
        return Dialog(self.session.window(), widget)

    def on_correct_measured_response_method(self):
        from madgui.widget.correct.mor_dialog import CorrectorWidget
        from madgui.widget.dialog import Dialog
        self.read_all()
        widget = CorrectorWidget(self.session)
        return Dialog(self.session.window(), widget)

    # helper functions

    def write_params(self, params):
        write = self.backend.write_param
        for param, value in params:
            write(param, value)
        self.backend.execute()

    def read_param(self, name):
        return self.backend.read_param(name)


class BeamSampler:

    """
    Beam surveillance utility.

    Keeps track of BPMs and broadcasts new readouts.
    """

    updated = Signal([int, dict])

    def __init__(self, control, monitors=()):
        self.monitors = monitors
        self._control = control
        self._timer = QTimer()
        self._timer.timeout.connect(self._poll)
        self._timer.start(500)
        self._confirmed = {}
        self._candidate = None
        self._confirmed_time = 0
        self._candidate_time = None
        self.readouts_list = List()

    @property
    def readouts(self):
        return self._confirmed

    @property
    def timestamp(self):
        return self._confirmed_time

    def _poll(self):
        if not self._control.is_connected():
            return
        readouts = {
            name: self._control.read_monitor(name)
            for name in self.monitors
        }
        if readouts == self._candidate:
            activity = {
                k: v
                for k, v in readouts.items()
                if v != self._confirmed.get(k)
            }
            self._candidate = None
            self._confirmed = readouts
            self._confirmed_time = self._candidate_time
            self.readouts_list[:] = self.fetch(self.monitors)
            self.updated.emit(self._candidate_time, activity)
        elif readouts != self._confirmed:
            self._candidate = readouts
            self._candidate_time = time.time()

    def fetch(self, monitors):
        readouts = self.readouts
        return [
            MonitorReadout(mon, readouts.get(mon.lower(), {}))
            for mon in monitors
        ]


class MonitorReadout:

    def __init__(self, name, values):
        self.name = name
        self.data = values
        self.posx = posx = values.get('posx')
        self.posy = posy = values.get('posy')
        self.envx = envx = values.get('envx')
        self.envy = envy = values.get('envy')
        self.valid = (envx is not None and envx > 0 and
                      envy is not None and envy > 0 and
                      not np.isclose(posx, -9.999) and
                      not np.isclose(posy, -9.999))
