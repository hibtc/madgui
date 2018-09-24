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
    """

    def __init__(self, frame):
        """
        Add plugin to the frame.

        Add a menu that can be used to connect to the online control. When
        connected, the plugin can be used to access parameters in the online
        database. This works only if the corresponding parameters were named
        exactly as in the database and are assigned with the ":=" operator.
        """
        super().__init__()
        self._frame = frame
        self.backend = None
        self.model = frame.model
        self.readouts = List()
        # menu conditions
        self.is_connected = Bool(False)
        self.has_backend = Bool(False)
        self.can_connect = ~self.is_connected & self.has_backend
        self.has_sequence = self.is_connected & self.model
        self._config = config = frame.config.online_control
        self._settings = config.settings
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
        self.backend = cls(self._frame, self._settings)
        self.backend.connect()
        self._frame.context['csys'] = self.backend
        self.is_connected.set(True)
        self.model.changed.connect(self._on_model_changed)
        self._on_model_changed()

    def disconnect(self):
        self._settings = self.export_settings()
        self._frame.context.pop('csys', None)
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
        """Get list of :class:`ParamInfo`."""
        if not self.model():
            return []
        return list(filter(
            None, map(self.backend.param_info, self.model().globals)))

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
            SyncParamItem(
                knob, live.read_param(knob.name), model.read_param(knob.name))
            for knob in self.get_knobs()
        ]
        widget.data_key = 'dvm_parameters'
        self._show_dialog(widget, apply)

    def read_all(self, knobs=None):
        live = self.backend
        self.model().write_params([
            (knob.name, live.read_param(knob.name))
            for knob in knobs or self.get_knobs()
        ], "Read params from online control")

    def write_all(self, knobs=None):
        model = self.model()
        self.write_params([
            (knob.name, model.read_param(knob.name))
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
        return MonitorWidget(self, self.model(), self._frame)

    @SingleWindow.factory
    def orm_measure_widget(self):
        """Measure ORM for later analysis."""
        from madgui.widget.dialog import Dialog
        from madgui.online.orm_analysis import MeasureWidget
        widget = MeasureWidget(self, self.model(), self._frame)
        dialog = Dialog(self._frame)
        dialog.setWidget(widget)
        dialog.setWindowTitle("ORM scan")
        return dialog

    def _show_dialog(self, widget, apply=None, export=True):
        from madgui.widget.dialog import Dialog
        dialog = Dialog(self._frame)
        if export:
            dialog.setExportWidget(widget, self._frame.folder)
            dialog.serious.updateButtons()
        else:
            dialog.setWidget(widget, tight=True)
        # dialog.setWindowTitle()
        if apply is not None:
            dialog.accepted.connect(apply)
        dialog.show()
        return dialog

    def on_correct_multi_grid_method(self):
        import madgui.online.multi_grid as module
        from madgui.widget.dialog import Dialog

        varyconf = self.model().data.get('multi_grid', {})
        selected = next(iter(varyconf))

        self.read_all()

        method = module.Corrector(self, varyconf)
        method.setup(selected)

        widget = module.CorrectorWidget(method)
        dialog = Dialog(self._frame)
        dialog.setWidget(widget, tight=True)
        dialog.show()

    def on_correct_optic_variation_method(self):
        import madgui.online.optic_variation as module
        from madgui.widget.dialog import Dialog

        varyconf = self.model().data.get('optic_variation', {})
        selected = next(iter(varyconf))

        self.read_all()

        method = module.Corrector(self, varyconf)
        method.setup(selected)

        widget = module.CorrectorWidget(method)
        dialog = Dialog(self._frame)
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
