"""
Plugin that integrates a beamoptikdll UI into MadGUI.
"""

import logging
from importlib import import_module

import numpy as np

from madgui.core.signal import Object
from madgui.util.misc import SingleWindow
from madgui.util.collections import Bool, List, CachedList

# TODO: catch exceptions and display error messages
# TODO: automate loading DVM parameters via model and/or named hook


class Control(Object):

    """
    Plugin class for MadGUI.

    When connected, the plugin can be used to access parameters in the online
    database. This works only if the corresponding parameters were named
    exactly as in the database and are assigned with the ":=" operator.
    """

    def __init__(self, session):
        super().__init__()
        self.session = session
        self.backend = None
        self.model = session.model
        self.readouts = List()
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
        self.session.user_ns.csys = self.backend
        self.is_connected.set(True)
        self.model.changed.connect(self._on_model_changed)
        self._on_model_changed()

    def disconnect(self):
        self._settings = self.export_settings()
        self.session.user_ns.csys = None
        self.backend.disconnect()
        self.backend = None
        self.is_connected.set(False)
        self.model.changed.disconnect(self._on_model_changed)
        self._on_model_changed()

    def _on_model_changed(self):
        model = self.model()
        elems = self.is_connected() and model and model.elements or ()
        read_monitor = lambda i, n: MonitorReadout(n, self.read_monitor(n))
        self.monitors = CachedList(read_monitor, [
            elem.name
            for elem in elems
            if elem.base_name.lower().endswith('monitor')
            or elem.base_name.lower() == 'instrument'
        ])

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
            for knob in self.model().globals
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
        model, live = self.model(), self.backend
        widget.data = [
            SyncParamItem(info, live.read_param(name), model.read_param(name))
            for name, info in self.get_knobs().items()
        ]
        widget.data_key = 'dvm_parameters'
        self._show_dialog(widget, apply)

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
        from madgui.online.orm_analysis import MeasureWidget
        widget = MeasureWidget(self.session)
        dialog = Dialog(self.session.window())
        dialog.setWidget(widget)
        dialog.setWindowTitle("ORM scan")
        return dialog

    def _show_dialog(self, widget, apply=None, export=True):
        from madgui.widget.dialog import Dialog
        dialog = Dialog(self.session.window())
        if export:
            dialog.setExportWidget(widget, self.session.folder)
            dialog.serious.updateButtons()
        else:
            dialog.setWidget(widget, tight=True)
        # dialog.setWindowTitle()
        if apply is not None:
            dialog.accepted.connect(apply)
        dialog.show()
        return dialog

    def on_correct_multi_grid_method(self):
        from .multi_grid import CorrectorWidget
        from madgui.widget.dialog import Dialog
        self.read_all()
        widget = CorrectorWidget(self.session)
        dialog = Dialog(self.session.window())
        dialog.setWidget(widget, tight=True)
        dialog.show()

    def on_correct_optic_variation_method(self):
        from .optic_variation import CorrectorWidget
        from madgui.widget.dialog import Dialog
        self.read_all()
        widget = CorrectorWidget(self.session)
        dialog = Dialog(self.session.window())
        dialog.setWidget(widget, tight=True)
        dialog.show()

    # helper functions

    def write_params(self, params):
        write = self.backend.write_param
        for param, value in params:
            write(param, value)
        self.backend.execute()

    def read_param(self, name):
        return self.backend.read_param(name)


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
