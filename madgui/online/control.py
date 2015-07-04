"""
Plugin that integrates a beamoptikdll UI into MadGUI.
"""

from __future__ import absolute_import

import sys
import traceback

import numpy

from pydicti import dicti

from cpymad.types import Expression

from madgui.core import wx
from madgui.core.plugin import HookCollection, EntryPoint
from madgui.util import unit
from madgui.widget import menu
from madgui.widget.input import CancelAction, Cancellable, Dialog

from .beamoptikdll import BeamOptikDLL, ExecOptions
from .dvm_parameters import DVM_ParameterList
from .dvm_conversion import ParamImporter
from .util import load_yaml_resource
from .dialogs import (ImportParamWidget, ExportParamWidget,
                      MonitorWidget, OpticSelectWidget, OptikVarianzWidget)
from .stub import BeamOptikDllProxy




# TODO: catch exceptions and display error messages
# TODO: automate loading DVM parameters via model and/or named hook


def strip_prefix(name, prefix):
    """Strip a specified prefix substring from a string."""
    if name.startswith(prefix):
        return name[len(prefix):]
    else:
        return name


def load_config():
    """Return the builtin configuration."""
    return load_yaml_resource('hit.online_control', 'config.yml')


class Control(object):

    """
    Plugin class for MadGUI.
    """

    _BeamOptikDLL = BeamOptikDLL

    def __init__(self, frame, menubar):
        """
        Add plugin to the frame.

        Add a menu that can be used to connect to the online control. When
        connected, the plugin can be used to access parameters in the online
        database. This works only if the corresponding parameters were named
        exactly as in the database and are assigned with the ":=" operator.
        """
        if not (self._check_dll() or self._check_stub()):
            # Can't connect, so no point in showing anything.
            return
        self.hook = HookCollection(
            on_loaded_dvm_params=None)
        self._frame = frame
        self._dvm = None
        self._config = load_config()
        self._dvm_params = {}
        units = unit.from_config_dict(self._config['units'])
        self._utool = unit.UnitConverter(units)
        submenu = self.create_menu()
        menu.extend(frame, menubar, [submenu])

    def _check_dll(self):
        """Check if the 'Connect' menu item should be shown."""
        return self._BeamOptikDLL.check_library()

    def _check_stub(self):
        """Check if the 'Connect &test stub' menu item should be shown."""
        # TODO: check for debug mode?
        return True

    @property
    def _model_name(self):
        try:
            return self._segment.model.name.lower()
        except AttributeError:
            return 'all'

    def _check_dvm_params(self):
        if self._dvm_params:
            return
        for ep in EntryPoint('hit.dvm_parameters.load').slots:
            parlist = ep(self._model_name)
            if parlist:
                self.set_dvm_parameter_list(parlist)
                return
        self.load_dvm_parameter_list()
        if not self._dvm_params:
            raise CancelAction

    def create_menu(self):
        """Create menu."""
        Item = menu.CondItem
        Separator = menu.Separator
        items = []
        if self._check_dll():
            items += [
                Item('&Connect',
                     'Connect online control interface',
                     self.load_and_connect,
                     self.is_disconnected),
            ]
        if self._check_stub():
            items += [
                Item('Connect &test stub',
                     'Connect a stub version (for offline testing)',
                     self.load_and_connect_stub,
                     self.is_disconnected),
            ]
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
            Item('&Execute changes',
                 'Apply parameter written changes to magnets',
                 self.execute,
                 self.has_sequence),
            Separator,
            Item('Read &monitors',
                 'Read SD values (beam envelope/position) from monitors',
                 self.read_all_sd_values,
                 self.has_sequence),
            Separator,
            Item('Detect beam &alignment',
                 'Detect the beam alignment and momentum (Optikvarianz)',
                 self.on_find_initial_position,
                 self.has_sequence),
            Separator,
            Item('&Load DVM parameter list',
                 'Load list of DVM parameters',
                 self.load_dvm_parameter_list,
                 self.is_connected),
        ]
        return menu.Menu('&Online control', items)

    def is_connected(self):
        """Check if online control is connected."""
        return self.connected

    def is_disconnected(self):
        """Check if online control is disconnected."""
        return not self.connected

    def has_sequence(self):
        """Check if online control is connected and a sequence is loaded."""
        return self.connected and bool(self._segment)

    def load_and_connect(self):
        """Connect to online database."""
        try:
            self._dvm = self._BeamOptikDLL.load_library()
        except OSError:
            exc_str = traceback.format_exception_only(*sys.exc_info()[:2])
            wx.MessageBox("".join(exc_str),
                          'Failed to load DVM module',
                          wx.ICON_ERROR|wx.OK,
                          parent=self._frame)
            return
        self._connect()

    def load_and_connect_stub(self):
        """Connect a stub BeamOptikDLL (for offline testing)."""
        logger = self._frame.getLogger('hit.online_control.stub')
        proxy = BeamOptikDllProxy({}, logger)
        self.hook.on_loaded_dvm_params.connect(
            proxy._use_dvm_parameter_examples)
        self._dvm = self._BeamOptikDLL(proxy)
        self._connect()

    def _connect(self):
        """Connect to online database (must be loaded)."""
        self._dvm.GetInterfaceInstance()
        self._frame.env['dvm'] = self._dvm

    def disconnect(self):
        """Disconnect from online database."""
        del self._frame.env['dvm']
        self._dvm.FreeInterfaceInstance()

    @property
    def connected(self):
        """Check if the online control is connected."""
        return bool(self._dvm)

    @property
    def _segment(self):
        """Return the online control (:class:`madgui.component.Model`)."""
        panel = self._frame.GetActiveFigurePanel()
        if panel:
            return panel.view.segment
        return None

    def iter_dvm_params(self):
        """
        Iterate over all known DVM parameters belonging to elements in the
        current sequence.

        Yields tuples of the form (Element, list[DVM_Parameter]).
        """
        self._check_dvm_params()
        for mad_elem in self._segment.elements:
            try:
                el_name = mad_elem['name']
                dvm_par = self._dvm_params[el_name]
                yield (mad_elem, dvm_par)
            except KeyError:
                continue

    def iter_convertible_dvm_params(self):
        """
        Iterate over all DVM parameters that can be converted to/from MAD-X
        element attributes in the current sequence.

        Yields instances of type :class:`ParamConverterBase`.
        """
        for mad_elem, dvm_params in self.iter_dvm_params():
            try:
                importer = getattr(ParamImporter, mad_elem['type'])
            except AttributeError:
                continue
            for param in importer(mad_elem, dvm_params, self):
                yield param

    @Cancellable
    def read_all(self):
        """Read all parameters from the online database."""
        # TODO: cache and reuse 'active' flag for each parameter
        rows = [(param, param.get_value())
                for param in self.iter_convertible_dvm_params()]
        if not rows:
            wx.MessageBox('There are no readable DVM parameters in the current sequence. Note that this operation requires a list of DVM parameters to be loaded.',
                          'No readable parameters available',
                          wx.ICON_ERROR|wx.OK,
                          parent=self._frame)
            return
        with Dialog(self._frame) as dialog:
            selected = ImportParamWidget(dialog).Query(rows)
        self.read_these(selected)

    def read_these(self, params):
        """
        Import list of DVM parameters to MAD-X.

        :param list params: List of tuples (ParamConverterBase, dvm_value)
        """
        segment = self._segment
        madx = segment.session.madx
        strip_unit = segment.session.utool.strip_unit
        for param, dvm_value in params:
            mad_value = param.dvm2madx(dvm_value)
            plain_value = strip_unit(param.mad_symb, mad_value)
            madx.set_value(param.mad_name, plain_value)
        segment.twiss()

    @Cancellable
    def write_all(self):
        """Write all parameters to the online database."""
        rows = [(param, param.get_value())
                for param in self.iter_convertible_dvm_params()]
        if not rows:
            wx.MessageBox('There are no writable DVM parameters in the current sequence. Note that this operation requires a list of DVM parameters to be loaded.',
                          'No writable parameters available',
                          wx.ICON_ERROR|wx.OK,
                          parent=self._frame)
            return
        with Dialog(self._frame) as dialog:
            selected = ExportParamWidget(dialog).Query(rows)
        self.write_these(par for par, _ in selected)

    def write_these(self, params):
        """
        Set parameter values in DVM from a list of parameters.

        :param list params: List of ParamConverterBase
        """
        for par in params:
            par.set_value()

    def get_float_value(self, dvm_name):
        """Get a single float value from the online database."""
        return self._dvm.GetFloatValue(dvm_name)

    def set_float_value(self, dvm_name, value):
        """Set a single float value in the online database."""
        self._dvm.SetFloatValue(dvm_name, value)

    def get_value(self, param_type, dvm_name):
        """Get a single value from the online database with unit."""
        plain_value = self.get_float_value(dvm_name)
        return self._utool.add_unit(param_type.lower(), plain_value)

    def set_value(self, param_type, dvm_name, value):
        """Set a single parameter in the online database with unit."""
        plain_value = self._utool.strip_unit(param_type, value)
        self.set_float_value(dvm_name, plain_value)

    def execute(self, options=ExecOptions.CalcDif):
        """Execute changes (commits prioir set_value operations)."""
        self._dvm.ExecuteChanges(options)

    def iter_sd_values(self):
        """Yields (element, values) tuples for usable monitors."""
        for elem in self.iter_monitors():
            values = self.get_sd_values(elem['name'])
            if values:
                yield (elem, values)

    @Cancellable
    def read_all_sd_values(self):
        """Read out SD values (beam position/envelope)."""
        # TODO: cache list of used SD monitors
        rows = list(self.iter_sd_values())
        if not rows:
            wx.MessageBox('There are no usable SD monitors in the current sequence.',
                          'No usable monitors available',
                          wx.ICON_ERROR|wx.OK,
                          parent=self._frame)
            return
        with Dialog(self._frame) as dialog:
            selected = MonitorWidget(dialog).Query(rows)
        self.use_these_sd_values(selected)

    def use_these_sd_values(self, monitor_values):
        segment = self._segment
        utool = segment.session.utool
        for elem, values in monitor_values:
            sd = {}
            ex = segment.beam['ex']
            ey = segment.beam['ey']
            if 'widthx' in values:
                sd['betx'] = values['widthx'] ** 2 / ex
            if 'widthy' in values:
                sd['bety'] = values['widthy'] ** 2 / ey
            if 'posx' in values:
                sd['x'] = values['posx']
            if 'posy' in values:
                sd['y'] = values['posy']
            sd = utool.dict_normalize_unit(sd)
            element_info = segment.get_element_info(elem['name'])
            # TODO: show sd values in figure

    def get_sd_values(self, element_name):
        """Read out one SD monitor."""
        values = {}
        for feature in ('widthx', 'widthy', 'posx', 'posy'):
            # TODO: Handle usability of parameters individually
            try:
                val = self._get_sd_value(element_name, feature)
            except RuntimeError:
                return {}
            # TODO: move sanity check to later, so values will simply be
            # unchecked/grayed out, instead of removed completely
            # The magic number -9999.0 signals corrupt values.
            # FIXME: Sometimes width=0 is returned. ~ Meaning?
            if feature.startswith('width') and val.magnitude <= 0:
                return {}
            values[feature] = val
        return values

    def _get_sd_value(self, element_name, param_name):
        """Return a single SD value (with unit)."""
        element_name = strip_prefix(element_name, 'sd_')
        param_name = param_name
        sd_name = param_name + '_' + element_name
        plain_value = self._dvm.GetFloatValueSD(sd_name.upper())
        # NOTE: Values returned by SD monitors are in millimeter:
        return plain_value * unit.units.mm

    def iter_monitors(self):
        """Iterate SD monitor elements (element dicts) in current sequence."""
        for element in self._segment.elements:
            if element['type'].lower().endswith('monitor'):
                yield element

    def load_dvm_parameter_list(self):
        """Show a FileDialog to import a new DVM parameter list."""
        dlg = wx.FileDialog(
            self._frame,
            "Load DVM-Parameter list. The CSV file must be ';' separated and 'utf-8' encoded.",
            wildcard="CSV files (*.csv)|*.csv",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() != wx.ID_OK:
            return
        filename = dlg.GetPath()
        # TODO: let user choose the correct delimiter/encoding settings
        try:
            parlist = DVM_ParameterList.from_csv(filename, 'utf-8')
        except UnicodeDecodeError:
            wx.MessageBox('I can only load UTF-8 encoded files!',
                          'UnicodeDecodeError',
                          wx.ICON_ERROR|wx.OK,
                          parent=self._frame)
        else:
            self.set_dvm_parameter_list(parlist)

    def set_dvm_parameter_list(self, parlist):
        """Use specified DVM_ParameterList."""
        self._dvm_params = dicti(parlist._data)
        self.hook.on_loaded_dvm_params(self._dvm_params)

    def sync_from_db(self):
        params = [(param, param.get_value())
                  for param in self.iter_convertible_dvm_params()]
        self.read_these(params)

    @property
    def varyconf(self):
        return self._segment.model._data.get('align', {})

    @Cancellable
    def on_find_initial_position(self):
        segment = self._segment
        # TODO: sync elements attributes
        elements = segment.sequence.elements
        with Dialog(self._frame) as dialog:
            elems = OpticSelectWidget(dialog).Query(elements, self.varyconf)
        with Dialog(self._frame) as dialog:
            OptikVarianzWidget(dialog).Query(self, *elems)

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
