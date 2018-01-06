"""
Plugin that integrates a beamoptikdll UI into MadGUI.
"""

from functools import partial

from pkg_resources import iter_entry_points

from madqt.qt import QtGui
from madqt.core.base import Object
from madqt.util.collections import Bool
import madqt.core.menu as menu
from madqt.util.misc import suppress

from . import elements
from . import api

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
        self.can_connect = self._frame.has_workspace & ~self.is_connected
        self.has_sequence = self._frame.has_workspace & self.is_connected
        # plugins
        loaders = [
            loader
            for ep in iter_entry_points('madqt.online.PluginLoader')
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
        self._frame.user_ns['csys'] = self._plugin
        self.is_connected.value = True

    def disconnect(self):
        self._frame.user_ns.pop('csys', None)
        self._plugin.disconnect()
        self._plugin = None
        self.is_connected.value = False

    def toggle_jitter(self):
        # I know…
        jitter = self._plugin._dvm._lib.jitter = not self._plugin._dvm._lib.jitter

    def iter_elements(self, kind):
        """Iterate :class:`~madqt.online.elements.BaseElement` in the sequence."""
        return filter(None, [
            suppress(api.UnknownElement, cls, self._segment, el, self._plugin)
            for el in self._segment.elements
            for cls in [elements.get_element_class(el)]
            if cls and issubclass(cls, kind)
        ])

    def _params(self):
        # TODO: cache and reuse 'active' flag for each parameter
        from madqt.online.dialogs import SyncParamItem
        elems = [
            (el, el.dvm_backend.get(), el.mad2dvm(el.mad_backend.get()))
            for el in self.iter_elements(elements.BaseMagnet)
        ]
        rows = [
            SyncParamItem(el.dvm_params[k], dv, mvals[k])
            for el, dvals, mvals in elems
            for k, dv in dvals.items()
        ]
        if not rows:
            QtGui.QMessageBox.warning(
                self._frame,
                'No parameters available'
                'There are no DVM parameters in the current sequence. Note that this operation requires a list of DVM parameters to be loaded.')
        return elems, rows

    def on_read_all(self):
        """Read all parameters from the online database."""
        elems, rows = self._params()
        if not rows:
            return
        from madqt.online.dialogs import ImportParamWidget
        widget = ImportParamWidget()
        widget.data = rows
        widget.data_key = 'dvm_parameters'
        self._show_dialog(widget, lambda: self.read_these(elems))

    def on_write_all(self):
        """Write all parameters to the online database."""
        elems, rows = self._params()
        if not rows:
            return
        from madqt.online.dialogs import ExportParamWidget
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

    def on_read_monitors(self):
        """Read out SD values (beam position/envelope)."""
        from madqt.online.dialogs import MonitorWidget, MonitorItem

        # TODO: cache list of used SD monitors
        rows = [MonitorItem(m.name, m.dvm_backend.get())
                for m in self.iter_elements(elements.Monitor)]
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
        from madqt.widget.dialog import Dialog
        dialog = Dialog(self._frame)
        dialog.setExportWidget(widget, self._frame.folder)
        # dialog.setWindowTitle()
        if apply is not None:
            dialog.applied.connect(apply)
        dialog.show()
        return dialog

    def on_correct_optic_variation_method(self):
        import madqt.correct.optic_variation as module
        varyconf = self._segment.workspace.data.get('optic_variation', {})
        self._correct(module, varyconf)

    def on_correct_multi_grid_method(self):
        import madqt.correct.multi_grid as module
        varyconf = self._segment.workspace.data.get('multi_grid', {})
        self._correct(module, varyconf)

    def _correct(self, module, varyconf):
        from madqt.widget.dialog import Dialog

        self.read_all()
        # TODO: open an orbit plot if none is present
        # self._frame.showTwiss('orbit')

        segment = self._segment
        elements = segment.elements

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
        from madqt.online.emittance import EmittanceDialog
        dialog = EmittanceDialog(self)
        dialog.show()
        return dialog

    # helper functions

    @property
    def _segment(self):
        """Return the online control."""
        workspace = self._frame.workspace
        return workspace and workspace.segment

    def read_these(self, params):
        """
        Import list of DVM parameters to MAD-X.

        :param list params: List of tuples (ParamConverterBase, dvm_value)
        """
        segment = self._segment
        for elem, dvm_value, mad_value in params:
            elem.mad_backend.set(elem.dvm2mad(dvm_value))
        segment.twiss.invalidate()

    def write_these(self, params):
        """
        Set parameter values in DVM from a list of parameters.

        :param list params: List of ParamConverterBase
        """
        for elem, dvm_value, mad_value in params:
            elem.dvm_backend.set(mad_value)
        self._plugin.execute()

    def get_element(self, elem_name):
        index = self._segment.get_element_index(elem_name.lower())
        elem = self._segment.elements[index]
        cls = elements.get_element_class(elem)
        return cls(self._segment, elem, self._plugin)
