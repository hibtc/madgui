# encoding: utf-8
"""
Provides unit conversion.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import sys

from pkg_resources import resource_filename

import numpy as np
from six import string_types as basestring
import pint

from pydicti import dicti

from madqt.util.symbol import SymbolicValue

try:
    # special handling for cpymad.Expression if available
    from cpymad.types import Expression
except ImportError:
    Expression = ()


__all__ = [
    'units',
    'strip_unit',
    'isclose',
    'allclose',
    'tounit',
    'get_unit_label',
    'format_quantity',
    'get_raw_label',
    'from_config',
    'from_config_dict',
    'UnitConverter',
]


def initialize():
    # Make sure 'constants_en.txt' exists as well (it is imported by
    # 'default_en.txt'):
    consts_spec = resource_filename('madqt.data', 'constants_en.txt')
    units_spec = resource_filename('madqt.data', 'default_en.txt')
    units = pint.UnitRegistry(units_spec)

    # make `str(quantity)` slightly nicer
    if sys.version_info[0] == 3:
        units.default_format = 'P~'
    else:
        # NOTE: 'P' outputs non-ascii unicode symbols and therefore breaks
        # str(quantity) on python2 (UnicodeEncodeError).
        units.default_format = '~'

    # extend unit registry
    # NOTE: parsing %, ‰ doesn't work automatically yet in pint.
    units.define(u'ratio = []')
    units.define(u'percent = 0.01 ratio = %')
    units.define(u'permille = 0.001 ratio = ‰')
    return units


units = initialize()


def isclose(q1, q2):
    m1 = strip_unit(q1, get_unit(q1))
    m2 = strip_unit(q2, get_unit(q1))
    return np.isclose(m1, m2)


def allclose(q1, q2):
    return all(isclose(a, b) for a, b in zip(q1, q2))


def get_unit(quantity):
    if isinstance(quantity, units.Quantity):
        return units.Quantity(1, quantity.units)
    return None


def strip_unit(quantity, unit=None):
    """Convert the quantity to a plain float."""
    if quantity is None:
        return None
    if unit is None:
        try:
            return quantity.magnitude
        except AttributeError:
            return quantity
    if isinstance(unit, (list, tuple)):
        # FIXME: 'zip' truncates without warning if not enough units
        # are defined
        return [q.to(u).magnitude for q, u in zip(quantity, unit)]
    try:
        return quantity.to(unit).magnitude
    except AttributeError:
        return quantity


def toquantity(value):
    if value is None:
        return None
    if isinstance(value, units.Quantity):
        return value
    return units.Quantity(value)


def tounit(quantity, unit):
    """Cast the quantity to a specific unit."""
    if quantity is None:
        return None
    if unit is None:
        unit = 1
    return toquantity(quantity).to(toquantity(unit))


def get_unit_label(quantity):
    """Get name of the unit."""
    return '[' + get_raw_label(quantity) + ']'


def format_quantity(quantity, num_spec=''):
    """Get a nice display string for the quantity."""
    num_fmt = '{:' + num_spec + '}'
    if isinstance(quantity, units.Quantity):
        magn = num_fmt.format(quantity.magnitude)
        unit = get_raw_label(quantity)
        return magn + ' ' + unit
    else:
        return num_fmt.format(quantity)


def get_raw_label(quantity):
    """Get the name of the unit, without enclosing brackets."""
    if quantity is None:
        return ''
    if not isinstance(quantity, units.Quantity):
        return str(quantity)
    short = pint.unit.UnitsContainer(
        {units._get_symbol(key): value
         for key, value in quantity.units.items()})
    as_ratio = any(exp > 0 for _, exp in short.items())
    return pint.formatting.formatter(
        short.items(),
        as_ratio=as_ratio,
        single_denominator=True,
        product_fmt=u'·',
        division_fmt=u'/',
        power_fmt=u'{0}{1}',
        parentheses_fmt=u'({0})',
        exp_call=pint.formatting._pretty_fmt_exponent,
    )


def from_config(unit):
    """
    Parse a config entry for a unit to a :class:`pint.unit.Quantity` instance.

    The pint parser is quite powerful. Valid examples are:

        s / m²
        microsecond
        10 rad
        m^-2
    """
    if not unit:
        return units(None)
    if isinstance(unit, list):
        return [from_config(u) for u in unit]
    if isinstance(unit, bytes):
        unit = unit.decode('utf-8')
    unit = u'{}'.format(unit)
    # as of pint-0.6 the following symbols fail to be parsed on python2:
    unit = unit.replace(u'µ', u'micro')
    unit = unit.replace(u'%', u'percent')
    unit = unit.replace(u'‰', u'permille')
    unit = unit.replace(u'Ω', u'ohm')
    return units(unit)


class UnitConverter(object):

    """
    Quantity converter.

    Used to add and remove units from quanitities and evaluate expressions.

    :ivar dict _units: unit dictionary
    """

    def __init__(self, units):
        self._units = dicti(units)

    @classmethod
    def from_config_dict(cls, conf_dict):
        """Convert a config dict of units to their in-memory representation."""
        return cls({k: from_config(v) for k, v in conf_dict.items()})

    def get_unit_label(self, name):
        """Get the name of the unit for the specified parameter name."""
        units = self._units
        return get_unit_label(units[name]) if name in units else ''

    def add_unit(self, name, value):
        """Add units to a single number."""
        units = self._units
        if name in units:
            if isinstance(value, (list, tuple)):
                # FIXME: 'zip' truncates without warning if not enough units
                # are defined
                return [self._add_unit(v, u)
                        for v, u in zip(value, units[name])]
            return self._add_unit(value, units[name])
        else:
            return value

    def _add_unit(self, value, unit):
        if isinstance(value, Expression):
            return SymbolicValue(value.expr, value.value, unit)
        else:
            return unit * value

    def strip_unit(self, name, value):
        """Convert to MAD-X units."""
        units = self._units
        return strip_unit(value, units[name]) if name in units else value

    def dict_add_unit(self, obj):
        """Add units to all elements in a dictionary."""
        return obj.__class__({k: self.add_unit(k, obj[k]) for k in obj})

    def dict_strip_unit(self, obj):
        """Remove units from all elements in a dictionary."""
        return obj.__class__({k: self.strip_unit(k, obj[k]) for k in obj})

    def normalize_unit(self, name, value):
        """Normalize unit to unit used in MAD-X."""
        units = self._units
        if name in units:
            if not isinstance(value, Expression):
                return tounit(value, units[name])
        return value

    def dict_normalize_unit(self, obj):
        """Normalize unit for all elements in a dictionary."""
        return obj.__class__({k: self.normalize_unit(k, obj[k]) for k in obj})
