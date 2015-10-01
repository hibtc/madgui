# encoding: utf-8
"""
Plugin that integrates a beamoptikdll UI into MadGUI.
"""

from __future__ import absolute_import

from functools import partial

from madgui.core import wx
from madgui.core.plugin import EntryPoint
from madgui.widget import menu
from madgui.widget.input import Cancellable, Dialog, ShowModal

from . import api
from . import dialogs
from . import ovm
from . import elements

# TODO: catch exceptions and display error messages
# TODO: automate loading DVM parameters via model and/or named hook


class Control(object):

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
        loaders = [
            loader
            for loader in EntryPoint('madgui.online.PluginLoader').slots
            if loader.check_avail()
        ]
        if loaders:
            submenu = self.create_menu(loaders)
            menu.extend(frame, menubar, [submenu])

    def create_menu(self, loaders):
        """Create menu."""
        Item = menu.CondItem
        Separator = menu.Separator
        items = []
        for loader in loaders:
            items.append(
                Item('Connect ' + loader.title,
                     'Connect ' + loader.descr,
                     partial(self.connect, loader),
                     lambda: bool(self._segment) and not self.is_connected())
            )
        items += [
            Item('&Disconnect',
                 'Disconnect online control interface',
                 self.disconnect,
                 self.is_connected),
            Separator,
            Item('&Read strengthes',
                 'Read magnet strengthes from the online database',
                 self.read_all,
                 self.has_sequence),
            Item('&Write strengthes',
                 'Write magnet strengthes to the online database',
                 self.write_all,
                 self.has_sequence),
            Separator,
            Item('Read &monitors',
                 'Read SD values (beam envelope/position) from monitors',
                 self.read_monitors,
                 self.has_sequence),
            Separator,
            Item('Detect beam &alignment',
                 'Detect the beam alignment and momentum (Optikvarianz)',
                 self.on_find_initial_position,
                 self.has_sequence),
        ]
        return menu.Menu('&Online control', items)

    # menu conditions

    def is_connected(self):
        """Check if the online control is connected."""
        return bool(self._plugin)

    def has_sequence(self):
        """Check if online control is connected and a sequence is loaded."""
        return self.is_connected() and bool(self._segment)

    # menu handlers

    def connect(self, loader):
        self._plugin = loader.load(self._frame)
        self._frame.env['dvm'] = self._plugin._dvm

    def disconnect(self):
        del self._frame.env['dvm']
        self._plugin.disconnect()
        self._plugin = None

    def iter_elements(self, kind=None):
        """Iterate :class:`elements.BaseElement` in the sequence."""
        if kind is None:
            kind = elements.BaseElement
        for el in self._segment.elements:
            try:
                cls = elements.get_element_class(el)
                if issubclass(cls, kind):
                    yield cls(self._segment, el, self._plugin)
            except api.UnknownElement:
                pass

    @Cancellable
    def read_all(self):
        """Read all parameters from the online database."""
        # TODO: cache and reuse 'active' flag for each parameter
        elems = [
            (el, el.dvm_backend.get(), el.mad2dvm(el.mad_backend.get()))
            for el in self.iter_elements(elements.BaseMagnet)
        ]
        rows = [
            (el.dvm_params[k], dv, mvals[k])
            for el, dvals, mvals in elems
            for k, dv in dvals.items()
        ]
        if not rows:
            wx.MessageBox('There are no readable DVM parameters in the current sequence. Note that this operation requires a list of DVM parameters to be loaded.',
                          'No readable parameters available',
                          wx.ICON_ERROR|wx.OK,
                          parent=self._frame)
            return
        with Dialog(self._frame) as dialog:
            dialogs.ImportParamWidget(dialog).Query(rows)
        self.read_these(elems)

    @Cancellable
    def write_all(self):
        """Write all parameters to the online database."""
        elems = [
            (el, el.dvm_backend.get(), el.mad2dvm(el.mad_backend.get()))
            for el in self.iter_elements(BaseMagnet)
        ]
        rows = [
            (el.dvm_params[k], dv, mvals[k])
            for el, dvals, mvals in elems
            for k, dv in dvals.items()
        ]
        if not rows:
            wx.MessageBox('There are no writable DVM parameters in the current sequence. Note that this operation requires a list of DVM parameters to be loaded.',
                          'No writable parameters available',
                          wx.ICON_ERROR|wx.OK,
                          parent=self._frame)
            return
        with Dialog(self._frame) as dialog:
            dialogs.ExportParamWidget(dialog).Query(rows)
        self.write_these(elems)

    @Cancellable
    def read_monitors(self):
        """Read out SD values (beam position/envelope)."""
        # TODO: cache list of used SD monitors
        rows = [(m.name, m.dvm_backend.get())
                for m in self.iter_elements(elements.Monitor)]
        if not rows:
            wx.MessageBox('There are no usable SD monitors in the current sequence.',
                          'No usable monitors available',
                          wx.ICON_ERROR|wx.OK,
                          parent=self._frame)
            return
        with Dialog(self._frame) as dialog:
            dialogs.MonitorWidget(dialog).Query(rows)
        # TODO: show SD values in plot?

    @Cancellable
    def on_find_initial_position(self):
        segment = self._segment
        # TODO: sync elements attributes
        elems = segment.sequence.elements
        varyconf = segment.model._data.get('align', {})
        with Dialog(self._frame) as dialog:
            elems = ovm.OpticSelectWidget(dialog).Query(elems, varyconf)
        data = ovm.OpticVariationMethod(self, *elems)
        with ovm.OpticVariationWizard(self._frame, data) as dialog:
            ShowModal(dialog)

    # helper functions

    @property
    def _segment(self):
        """Return the online control (:class:`madgui.component.Model`)."""
        panel = self._frame.GetActiveFigurePanel()
        return panel and panel.view.segment

    def read_these(self, params):
        """
        Import list of DVM parameters to MAD-X.

        :param list params: List of tuples (ParamConverterBase, dvm_value)
        """
        segment = self._segment
        madx = segment.session.madx
        strip_unit = segment.session.utool.strip_unit
        for elem, dvm_value, mad_value in params:
            elem.mad_backend.set(elem.dvm2mad(dvm_value))
        segment.twiss()

    def write_these(self, params):
        """
        Set parameter values in DVM from a list of parameters.

        :param list params: List of ParamConverterBase
        """
        for elem, dvm_value, mad_value in params:
            elem.dvm_backend.set(mad_value)
        self._plugin.execute()

    def get_element(self, elem_name):
        index = self._segment.get_element_index(elem_name)
        elem = self._segment.elements[index]
        cls = elements.get_element_class(elem)
        return cls(self._segment, elem, self._plugin)
