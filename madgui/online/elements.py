# encoding: utf-8
"""
This module exposes a uniform wrapper API for various MAD-X element types.
There are for example at least three ways to define a dipole, all of them
having a different access API:

    - SBEND->ANGLE
    - MULTIPOLE->KNL[0]
    - MULTIPOLE->KSL[0]

Clearly, it would be too cumbersome (and impossible to maintain) to make this
case distinction in all the client code dealing with dipoles.

Therefore, :class:`BaseDipole` defines a common interface for dipoles. The
correct implementing class corresponding to a given MAD-X element can be
obtained via :func:`get_element_class`. For an example, see the code in
:mod:`control`.
"""

from __future__ import absolute_import

from madgui.util.symbol import SymbolicValue

from . import api
from . import mad_backend


__all__ = [
    'detect_multipole_order',
    'get_element_class',
    'BaseElement',
    'Monitor',
    'BaseMagnet',
    'BaseDipole',
    'Dipole',
    'MultipoleNDP',
    'MultipoleSDP',
    'BaseQuadrupole',
    'Quadrupole',
    'MultipoleNQP',
    'MultipoleSQP',
    'Solenoid',
]


def detect_multipole_order(coefs):
    """Get the multipole order from a given KNL or KSL coefficient array."""
    # TODO: safe-guard against mixed orders
    # TODO: also handle non-expression scalars?
    for i, c in enumerate(coefs):
        if isinstance(c, SymbolicValue):
            return i
    return None


def get_element_class(element):
    """Get the implementing class for a given MAD-X element."""
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
        n = detect_multipole_order(element.get('knl', []))
        if n == 0: return MultipoleNDP
        if n == 1: return MultipoleNQP
        if n != None:
            raise api.UnknownElement
        n = detect_multipole_order(element.get('ksl', []))
        if n == 0: return MultipoleSDP
        if n == 1: return MultipoleSQP
        raise api.UnknownElement
        # TODO: handle mixed dip/quadp coefficients?
        # TODO: handle mixed knl/ksl coefficients?
        # TODO: handle higher order multipoles
    raise api.UnknownElement


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
        """Convert a set of MAD-X values to DVM values."""
        return self.dvm_converter.to_backend(
            self.mad_converter.to_standard(values))

    def dvm2mad(self, values):
        """Convert a set of DVM values to MAD-X values."""
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

    """Implementation for a MONITOR."""

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

    """Base interface for magnets."""

    def _mad_backend(self):
        return self._construct(self.mad_cls())

    @property
    def dvm_params(self):
        return self.dvm_converter.param_info


class BaseDipole(BaseMagnet):

    """Base interface for dipoles."""

    parameter_info = {'angle': "Total deflection angle."}

    def _dvm_backend(self):
        return self._plugin.get_dipole(self._segment, self.elements, self.skew)


class Dipole(BaseDipole):
    """Implementation for a dipole defined as SBEND."""
    skew = False
    mad_cls = mad_backend.Dipole
    # TODO: what about DIPEDGE?


class MultipoleNDP(BaseDipole):
    """Implementation for a dipole defined as MULTIPOLE with KNL."""
    skew = False
    mad_cls = mad_backend.MultipoleNDP


class MultipoleSDP(BaseDipole):
    """Implementation for a dipole defined as MULTIPOLE with KSL."""
    skew = True
    mad_cls = mad_backend.MultipoleSDP


class BaseQuadrupole(BaseMagnet):

    """Base interface for quadrupoles."""

    parameter_info = {'kL': "Integrated quadrupole field strength."}

    def _dvm_backend(self):
        return self._plugin.get_quadrupole(self._segment, self.elements)


class Quadrupole(BaseQuadrupole):

    """Implementation for a QUADRUPOLE."""

    def _mad_backend(self):
        # TODO: use 'lrad' instead of 'l' when needed?
        return self._construct(mad_backend.Quadrupole(self.elements[0]['l']))


class MultipoleNQP(BaseQuadrupole):
    """Implementation for a quadrupole defined as MULTIPOLE with KNL."""
    mad_cls = mad_backend.MultipoleNQP


class MultipoleSQP(BaseQuadrupole):
    """Implementation for a quadrupole defined as MULTIPOLE with KSL."""
    mad_cls = mad_backend.MultipoleSQP


class Solenoid(BaseMagnet):

    """Implementation for SOLENOID element."""

    parameter_info = {'ks': "Integrated field strength."}
    mad_cls = mad_backend.Solenoid

    def _dvm_backend(self):
        return self._plugin.get_solenoid(self._segment, self.elements)
