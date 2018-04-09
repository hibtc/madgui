"""
Plugin that integrates a beamoptikdll UI into MadGUI.
"""

from madgui.qt import QtGui
from madgui.core.base import Object
from madgui.util.misc import SingleWindow
from madgui.util.collections import Bool

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
        self._plugin = None
        # menu conditions
        self.is_connected = Bool(False)
        self.can_connect = ~self.is_connected
        self.has_sequence = self.is_connected & frame.has_model

    # menu handlers

    def connect(self, loader):
        self._plugin = loader.load(self._frame)
        self._plugin.connect()
        self._frame.context['csys'] = self._plugin
        self.is_connected.set(True)

    def disconnect(self):
        self._frame.context.pop('csys', None)
        self._plugin.disconnect()
        self._plugin = None
        self.is_connected.set(False)

    def toggle_jitter(self):
        # I know…
        self._plugin._dvm._lib.jitter = not self._plugin._dvm._lib.jitter

    def get_knobs(self):
        """Get list of knobs, returned as tuples `(mad,dvm)`."""
        if not self._model:
            return []
        return [
            (knob_mad, knob_dvm)
            for knob_mad in self._model.get_knobs()
            for knob_dvm in [self._plugin.get_knob(knob_mad)]
            if knob_dvm
        ]

    def _params(self):
        # TODO: cache and reuse 'active' flag for each parameter
        from madgui.online.dialogs import SyncParamItem
        knobs = [
            (mknob, mknob.read(),
             dknob, dknob.read())
            for mknob, dknob in self.get_knobs()
        ]
        rows = [
            SyncParamItem(self._plugin.param_info(dknob),
                          dval, mval, dknob.attr)
            for mknob, mval, dknob, dval in knobs
        ]
        return knobs, rows

    def on_read_all(self):
        """Read all parameters from the online database."""
        elems, rows = self._params()
        if not rows:
            return
        from madgui.online.dialogs import ImportParamWidget
        widget = ImportParamWidget()
        widget.data = rows
        widget.data_key = 'dvm_parameters'
        self._show_dialog(widget, lambda: self.read_these(elems))

    def on_write_all(self):
        """Write all parameters to the online database."""
        elems, rows = self._params()
        if not rows:
            return
        from madgui.online.dialogs import ExportParamWidget
        widget = ExportParamWidget()
        widget.data = rows
        widget.data_key = 'dvm_parameters'
        self._show_dialog(widget, lambda: self.write_these(elems))

    def read_all(self):
        elems, rows = self._params()
        self.read_these(elems)

    def write_all(self):
        elems, rows = self._params()
        self.write_these(elems)

    def on_read_beam(self):
        # TODO: add confirmation dialog
        self.read_beam()

    def read_beam(self):
        self._model.set_beam(self._plugin.get_beam())

    def read_monitor(self, name):
        return self._plugin.read_monitor(name)

    @SingleWindow.factory
    def monitor_widget(self):
        """Read out SD values (beam position/envelope)."""
        from madgui.online.dialogs import MonitorWidget
        widget = MonitorWidget(self, self._model, self._frame)
        widget.show()
        return widget

    def _show_dialog(self, widget, apply=None, export=True):
        from madgui.widget.dialog import Dialog
        dialog = Dialog(self._frame)
        if export:
            dialog.setExportWidget(widget, self._frame.folder)
        else:
            dialog.setWidget(widget, tight=True)
        # dialog.setWindowTitle()
        if apply is not None:
            dialog.applied.connect(apply)
        dialog.show()
        return dialog

    def on_correct_multi_grid_method(self):
        import madgui.correct.multi_grid as module
        from madgui.widget.dialog import Dialog

        varyconf = self._model.data.get('multi_grid', {})
        selected = next(iter(varyconf))

        self.read_all()

        method = module.Corrector(self, varyconf)
        method.setup(selected)

        widget = module.CorrectorWidget(method)
        dialog = Dialog(self._frame)
        dialog.setWidget(widget, tight=True)
        dialog.show()

    def on_correct_optic_variation_method(self):
        import madgui.correct.optic_variation as module
        from madgui.widget.dialog import Dialog
        varyconf = self._model.data.get('optic_variation', {})

        self.read_all()
        self._frame.open_graph('orbit')

        model = self._model
        elements = model.elements

        select = module.SelectWidget(elements, varyconf)
        dialog = Dialog(self._frame)
        dialog.setExportWidget(select, self._frame.folder)
        dialog.exec_()
        if dialog.result() != QtGui.QDialog.Accepted:
            return

        method = module.Corrector(self, *select.get_data())
        widget = module.CorrectorWidget(method)
        dialog = Dialog(self._frame)
        dialog.setWidget(widget)
        dialog.show()

    def on_emittance_measurement(self):
        from madgui.online.emittance import EmittanceDialog
        dialog = EmittanceDialog(self)
        dialog.show()
        return dialog

    # helper functions

    @property
    def _model(self):
        """Return the online control."""
        return self._frame.model

    def read_these(self, params):
        """
        Import list of DVM parameters to MAD-X.

        :param list params: List of tuples (ParamConverterBase, dvm_value)
        """
        for mknob, mval, dknob, dval in params:
            mknob.write(dval)

    def write_these(self, params):
        """
        Set parameter values in DVM from a list of parameters.

        :param list params: List of ParamConverterBase
        """
        for mknob, mval, dknob, dval in params:
            dknob.write(mval)
        self._plugin.execute()
