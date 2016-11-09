# encoding: utf-8
"""
Plugin that integrates a beamoptikdll UI into MadGUI.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from functools import partial

from pkg_resources import iter_entry_points

from madqt.qt import QtGui
from madqt.core.base import Object, Signal
from madqt.util.collections import Bool
import madqt.core.menu as menu

from . import elements

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
        self._frame = frame
        self._plugin = None
        # menu conditions
        self.is_connected = Bool(False)
        self.can_connect = self._frame.has_universe & ~self.is_connected
        self.has_sequence = self._frame.has_universe & self.is_connected
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
                Item('Connect ' + loader.title, None,
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
                 self.read_all,
                 enabled=self.has_sequence),
            Item('&Write strengths', None,
                 'Write magnet strengths to the online database',
                 self.write_all,
                 enabled=self.has_sequence),
            Separator,
            Item('Read &monitors', None,
                 'Read SD values (beam envelope/position) from monitors',
                 self.read_monitors,
                 enabled=self.has_sequence),
            Separator,
            Item('&Orbit correction (2 optics)', None,
                 'Perform orbit correction (2 optics method)',
                 self.on_find_initial_position,
                 enabled=self.has_sequence),
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

    def iter_elements(self, kind):
        """Iterate :class:`~madqt.online.elements.BaseElement` in the sequence."""
        return filter(None, [
            cls(self._segment, el, self._plugin)
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

    def read_all(self):
        """Read all parameters from the online database."""
        elems, rows = self._params()
        if not rows:
            return
        from madqt.online.dialogs import ImportParamWidget
        widget = ImportParamWidget()
        widget.data = rows
        widget.data_key = 'dvm_parameters'
        self._show_dialog(widget, lambda: self.read_these(elems))

    def write_all(self):
        """Write all parameters to the online database."""
        elems, rows = self._params()
        if not rows:
            return
        from madqt.online.dialogs import ExportParamWidget
        widget = ExportParamWidget()
        widget.data = rows
        widget.data_key = 'dvm_parameters'
        self._show_dialog(widget, lambda: self.write_these(elems))

    def read_monitors(self):
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

    def on_find_initial_position(self):
        from madqt.widget.dialog import Dialog
        from . import ovm

        segment = self._segment
        # TODO: sync elements attributes
        elements = segment.sequence.elements
        varyconf = segment.universe.data.get('align', {})
        # TODO: …

        widget = ovm.SelectWidget(elements, varyconf)
        dialog = Dialog(self._frame)
        dialog.setExportWidget(widget, self._frame.folder)
        dialog.exec_()

        choices = widget.get_data()

        method = ovm.OpticVariationMethod(self, *choices)
        widget = ovm.OVM_Widget(method)
        dialog = Dialog(self._frame)
        dialog.setWidget(widget)
        dialog.exec_()


    # helper functions

    @property
    def _segment(self):
        """Return the online control."""
        universe = self._frame.universe
        return universe and universe.segment

    def read_these(self, params):
        """
        Import list of DVM parameters to MAD-X.

        :param list params: List of tuples (ParamConverterBase, dvm_value)
        """
        segment = self._segment
        for elem, dvm_value, mad_value in params:
            elem.mad_backend.set(elem.dvm2mad(dvm_value))
        segment.retrack()

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
