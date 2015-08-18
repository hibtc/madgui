"""
Plugin that integrates a beamoptikdll UI into MadGUI.
"""

from __future__ import absolute_import

from functools import partial

import numpy

from cpymad.types import Expression

from madgui.core import wx
from madgui.core.plugin import EntryPoint
from madgui.util.common import cachedproperty
from madgui.widget import menu
from madgui.widget.input import Cancellable, Dialog

from . import api
from . import dialogs
from . import mad_backend

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
        """Iterate :class:`BaseElement` in the sequence."""
        if kind is None:
            kind = BaseElement
        for el in self._segment.elements:
            cls = self._decide_element(el)
            if cls and issubclass(cls, kind):
                try:
                    yield cls(self._segment, el, self._plugin)
                except api.UnknownElement:
                    pass

    @Cancellable
    def read_all(self):
        """Read all parameters from the online database."""
        # TODO: cache and reuse 'active' flag for each parameter
        elements = [
            (el, el.dvm_backend.get(), el.mad2dvm(el.mad_backend.get()))
            for el in self.iter_elements(BaseMagnet)
        ]
        rows = [
            (el.dvm_params[k], dv, mvals[k])
            for el, dvals, mvals in elements
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
        self.read_these(elements)

    @Cancellable
    def write_all(self):
        """Write all parameters to the online database."""
        elements = [
            (el, el.dvm_backend.get(), el.mad2dvm(el.mad_backend.get()))
            for el in self.iter_elements(BaseMagnet)
        ]
        rows = [
            (el.dvm_params[k], dv, mvals[k])
            for el, dvals, mvals in elements
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
        self.write_these(elements)

    @Cancellable
    def read_monitors(self):
        """Read out SD values (beam position/envelope)."""
        # TODO: cache list of used SD monitors
        rows = [(m.name, m.dvm_backend.get())
                for m in self.iter_elements(Monitor)]
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
        elements = segment.sequence.elements
        with Dialog(self._frame) as dialog:
            elems = dialogs.OpticSelectWidget(dialog).Query(elements, self.varyconf)
        with Dialog(self._frame) as dialog:
            dialogs.OptikVarianzWidget(dialog).Query(self, *elems)

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

    def align_beam(self, elem):
        # TODO: use config only as default, but ask user
        varyconf = self.varyconf.get(mon['name'])
        if not varyconf:
            wx.MessageBox('Steerer for alignment not defined',
                          'No config for alignment',
                          wx.ICON_ERROR|wx.OK,
                          parent=self._frame)
            return
        vary = (varyconf['h-steerer'] +
                varyconf['v-steerer'])
        segment = self._segment
        madx = segment.session.madx
        utool = segment.session.utool
        constraints = [
            {'range': elem['name'], 'x': 0},
            {'range': elem['name'], 'px': 0},
            {'range': elem['name'], 'y': 0},
            {'range': elem['name'], 'py': 0},
            # TODO: also set betx, bety unchanged?
        ]
        madx.match(
            sequence=segment.sequence.name,
            vary=vary,
            constraints=constraints,
            twiss_init=utool.dict_strip_unit(segment.twiss_args))
        segment.hook.update()

        # TODO: read matched parameters from madx and set in online control

    def find_initial_position(self, monitor, quadrupole, kl_0, kl_1):
        """
        Find initial beam alignment + momentum based on two measurements of a
        monitor at different quadrupole strengths.
        """
        A, a = self._measure_with_optic(monitor, quadrupole, kl_0)
        B, b = self._measure_with_optic(monitor, quadrupole, kl_1)
        return self.compute_initial_position(A, a, B, b)

    def _measure_with_optic(self, monitor, quadrupole, kl):
        monitor = self._segment.get_element_info(monitor)
        quadrupole = self._segment.get_element_info(quadrupole)
        return (self._get_sectormap_with_optic(monitor, quadrupole, kl),
                self._read_monitor_with_optic(monitor, quadrupole, kl))

    def _get_sectormap_with_optic(self, monitor, quadrupole, kl):
        segment = self._segment
        madx = segment.session.madx
        strip_unit = segment.session.utool.strip_unit
        elements = segment.sequence.elements
        orig_k1 = elements[quadrupole.name]['k1']
        mad_name = monitor.name + '->k1'
        mad_value = strip_unit('kl', kl) / elements[quadrupole.name]['l']
        madx.set_value(mad_name, mad_value)
        try:
            return segment.get_transfer_map(segment.start, monitor)
        finally:
            if isinstance(orig_k1, Expression):
                madx.set_expression(mad_name, orig_k1)
            else:
                madx.set_value(mad_name, orig_k1)

    def _read_monitor_with_optic(self, monitor, quadrupole, kl):
        par_type = 'kL'
        dvm_name = 'kL_' + quadrupole.name
        sav_value = self.get_value(par_type, dvm_name)
        # TODO: use conversion utility to convert to a writeable parameter
        # (KL_* are read-only).
        dvm_value = kl
        self.set_value(par_type, dvm_name, dvm_value)
        self.execute()
        # TODO: have to wait here?
        try:
            return self.get_sd_values(monitor.name)
        finally:
            self.set_value(par_type, dvm_name, sav_value)
            self.execute()

    def _strip_sd_pair(self, sd_values, prefix='pos'):
        strip_unit = self._segment.session.utool.strip_unit
        return (strip_unit('x', sd_values[prefix + 'x']),
                strip_unit('y', sd_values[prefix + 'y']))

    def compute_initial_position(self, A, a, B, b):
        """
        Compute initial beam position from two monitor read-outs at different
        quadrupole settings.

        A, B are the 4D SECTORMAPs from start to the monitor.
        a, b are the 2D measurement vectors (x, y)

        This function solves the linear system:

                Ax = a
                Bx = b

        for the 4D phase space vector x and returns the result as a dict with
        keys 'x', 'px', 'y, 'py'.
        """
        utool = self._segment.session.utool
        zero = numpy.zeros((2,4))
        eye = numpy.eye(4)
        s = ((0,2), slice(0,4))
        M = numpy.bmat([[A[s], zero],
                        [zero, B[s]],
                        [eye,  -eye]])
        m = (self._strip_sd_pair(a) +
             self._strip_sd_pair(b) +
             (0, 0, 0, 0))
        x = numpy.linalg.lstsq(M, m)[0]
        return utool.dict_add_unit({'x': x[0], 'px': x[1],
                                    'y': x[2], 'py': x[3]})

    def _decide_element(self, element):
        el_name = element['name'].lower()
        el_type = element['type'].lower()
        if el_type.endswith('monitor'):
            return Monitor
        # TODO: pass dvm params
        if el_type == 'sbend':
            return Dipole
        if el_type == 'quadrupole':
            return Quadrupole
        if el_type == 'solenoid':
            return Solenoid
        if el_type == 'multipole':
            try:
                n = len(element['knl'])
            except KeyError:
                pass
            else:
                if n == 1: return MultipoleNDP
                if n == 2: return MultipoleNQP
                return None
            try:
                n = len(element['ksl'])
            except KeyError:
                pass
            else:
                if n == 1: return MultipoleSDP
                if n == 2: return MultipoleSQP
                return None
            # TODO: handle mixed dip/quadp coefficients?
            # TODO: handle higher order multipoles


class BaseElement(api._Interface):

    """
    Logical beam line element.

    Can be implemented as a group of related MAD-X elements, but usually
    refers to the same physical element.
    """

    def __init__(self, segment, element, plugin):
        self.name = element['name']
        self.el_type = element['type']
        self.elements = (element,)
        self._segment = segment
        self._plugin = plugin
        self.mad_converter, self.mad_backend = self._mad_backend()
        self.dvm_converter, self.dvm_backend = self._dvm_backend()

    @api.abstractproperty
    def parameter_info(self):
        """Get a parameter description dict."""

    @api.abstractmethod
    def _mad_backend(self):
        """Get converter + backend classes for MAD-X."""

    @api.abstractmethod
    def _dvm_backend(self):
        """Get converter + backend classes for DB."""

    def mad2dvm(self, values):
        return self.dvm_converter.to_backend(
            self.mad_converter.to_standard(values))

    def dvm2mad(self, values):
        return self.mad_converter.to_backend(
            self.dvm_converter.to_standard(values))

    # mixin:
    def _construct(self, conv):
        elem = self.elements[0]
        madx = self._segment.madx
        utool = self._segment.session.utool
        lval = {
            key: mad_backend._get_property_lval(elem, key)
            for key in conv.backend_keys
        }
        back = mad_backend.MagnetBackend(madx, utool, elem, lval)
        return conv, back


class Monitor(BaseElement):

    parameter_info = {
        'widthx': 'Beam x width',
        'widthy': 'Beam y width',
        'posx': 'Beam x position',
        'posy': 'Beam y position',
    }

    def _mad_backend(self):
        segment = self._segment
        conv = mad_backend.Monitor(segment.beam['ex'], segment.beam['ey'])
        back = mad_backend.MonitorBackend(segment, self.elements[0])
        return conv, back

    def _dvm_backend(self):
        return self._plugin.get_monitor(self._segment, self.elements)


class BaseMagnet(BaseElement):

    def _mad_backend(self):
        return self._construct(self.mad_cls())

    @property
    def dvm_params(self):
        return self.dvm_converter.param_info


class BaseDipole(BaseMagnet):

    parameter_info = {'angle': "Total deflection angle."}

    def _dvm_backend(self):
        return self._plugin.get_dipole(self._segment, self.elements, self.skew)


class Dipole(BaseDipole):
    skew = False
    mad_cls = mad_backend.Dipole
    # TODO: what about DIPEDGE?


class MultipoleNDP(BaseDipole):
    skew = False
    mad_cls = mad_backend.MultipoleNDP


class MultipoleSDP(BaseDipole):
    skew = True
    mad_cls = mad_backend.MultipoleSDP


class BaseQuadrupole(BaseMagnet):

    parameter_info = {'kL': "Integrated quadrupole field strength."}

    def _dvm_backend(self):
        return self._plugin.get_quadrupole(self._segment, self.elements)


class Quadrupole(BaseQuadrupole):

    def _mad_backend(self):
        # TODO: use 'lrad' instead of 'l' when needed?
        return self._construct(mad_backend.Quadrupole(self.elements[0]['l']))


class MultipoleNQP(BaseQuadrupole):
    mad_cls = mad_backend.MultipoleNQP


class MultipoleSQP(BaseQuadrupole):
    mad_cls = mad_backend.MultipoleSQP


class Solenoid(BaseMagnet):

    parameter_info = {'ks': "Integrated field strength."}
    mad_cls = mad_backend.Solenoid

    def _dvm_backend(self):
        return self._plugin.get_solenoid(self._segment, self.elements)
