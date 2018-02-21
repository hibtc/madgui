"""
Plugin that integrates a beamoptikdll UI into MadGUI.
"""

# TODO: steerer corrections should be in DVM units

from functools import partial

from pkg_resources import iter_entry_points

from madgui.qt import QtGui
from madgui.core.base import Object
from madgui.util.collections import Bool
import madgui.core.menu as menu

# TODO: catch exceptions and display error messages
# TODO: automate loading DVM parameters via model and/or named hook


class Control(Object):

    """
    Plugin class for MadGUI.
    """

    def __init__(self, frame, menubar):
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
        # plugins
        loaders = [
            loader
            for ep in iter_entry_points('madgui.online.PluginLoader')
            for loader in [ep.load()]
            if loader.check_avail()
        ]
        if loaders:
            submenu = self.create_menu(loaders)
            menu.extend(frame, menubar, [submenu])

    def create_menu(self, loaders):
        """Create menu."""
        Item = menu.Item
        Separator = menu.Separator
        items = []
        for loader in loaders:
            items.append(
                Item('Connect ' + loader.title, loader.hotkey,
                     'Connect ' + loader.descr,
                     partial(self.connect, loader),
                     enabled=self.can_connect))
        items += [
            Item('&Disconnect', None,
                 'Disconnect online control interface',
                 self.disconnect,
                 enabled=self.is_connected),
            Separator,
            Item('&Read strengths', None,
                 'Read magnet strengths from the online database',
                 self.on_read_all,
                 enabled=self.has_sequence),
            Item('&Write strengths', None,
                 'Write magnet strengths to the online database',
                 self.on_write_all,
                 enabled=self.has_sequence),
            Item('Read &beam', None,
                 'Read beam settings from the online database',
                 self.on_read_beam,
                 enabled=self.has_sequence),
            Separator,
            Item('Read &monitors', None,
                 'Read SD values (beam envelope/position) from monitors',
                 self.on_read_monitors,
                 enabled=self.has_sequence),
            Separator,
            menu.Menu('&Orbit correction', [
                Item('Optic &variation', 'Ctrl+V',
                     'Perform orbit correction via 2-optics method',
                     self.on_correct_optic_variation_method,
                     enabled=self.has_sequence),
                Item('Multi &grid', 'Ctrl+G',
                     'Perform orbit correction via 2-grids method',
                     self.on_correct_multi_grid_method,
                     enabled=self.has_sequence),
            ]),
            Item('&Emittance measurement', 'Ctrl+E',
                 'Perform emittance measurement using at least 3 monitors',
                 self.on_emittance_measurement,
                 enabled=self.has_sequence),
            Separator,
            menu.Menu('&Settings', [
                # TODO: dynamically fill by plugin
                Item('&Jitter', None,
                     'Random Jitter for test interface',
                     self.toggle_jitter,
                     enabled=self.is_connected,
                     checked=True),
            ]),
        ]
        return menu.Menu('&Online control', items)

    # menu handlers

    def connect(self, loader):
        self._plugin = loader.load(self._frame)
        self._plugin.connect()
        self._frame.user_ns['csys'] = self._plugin
        self.is_connected.value = True

    def disconnect(self):
        self._frame.user_ns.pop('csys', None)
        self._plugin.disconnect()
        self._plugin = None
        self.is_connected.value = False

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
            for knob_dvm in [self._plugin.get_knob(knob_mad.elem, knob_mad.attr)]
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
                          dval, mknob.to(dknob.attr, mval))
            for mknob, mval, dknob, dval in knobs
        ]
        if not rows:
            QtGui.QMessageBox.warning(
                self._frame,
                'No parameters available',
                'There are no DVM parameters in the current sequence. Note that this operation requires a list of DVM parameters to be loaded.')
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

    def on_read_monitors(self):
        """Read out SD values (beam position/envelope)."""
        from madgui.online.dialogs import MonitorWidget, MonitorItem

        # TODO: cache list of used SD monitors
        rows = [MonitorItem(el.Name, self.read_monitor(el.Name))
                for el in self._model.elements
                if el.Type.lower().endswith('monitor')
                or el.Type.lower() == 'instrument']
        if not rows:
            QtGui.QMessageBox.critical(
                self._frame,
                'No usable monitors available',
                'There are no usable SD monitors in the current sequence.')
            return

        widget = MonitorWidget()
        widget.data = rows
        widget.data_key = 'monitor_values'
        self._show_dialog(widget)
        # TODO: show SD values in plot?

    def _show_dialog(self, widget, apply=None):
        from madgui.widget.dialog import Dialog
        dialog = Dialog(self._frame)
        dialog.setExportWidget(widget, self._frame.folder)
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
        # TODO: open an orbit plot if none is present
        # self._frame.showTwiss('orbit')

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
            mknob.write(dknob.to(mknob.attr, dval))

    def write_these(self, params):
        """
        Set parameter values in DVM from a list of parameters.

        :param list params: List of ParamConverterBase
        """
        for mknob, mval, dknob, dval in params:
            dknob.write(mknob.to(dknob.attr, mval))
        self._plugin.execute()
