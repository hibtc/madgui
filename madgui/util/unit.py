# encoding: utf-8
"""
Provides unit conversion.
"""

# force new style imports
from __future__ import absolute_import

# stdlib
import sys

# 3rd party
import pint
from pydicti import dicti
from cpymad.types import Expression

# internal
from madgui.util.symbol import SymbolicValue


# exported symbols
__all__ = ['units',
           'strip_unit',
           'tounit',
           'get_unit_label',
           'get_raw_label',
           'from_config',
           'from_config_dict',
           'UnitConverter']


# compatibility
try:                    # python2
    basestring
except NameError:       # python3 (let's think about future...)
    basestring = str
    unicode = str


units = pint.UnitRegistry()


# make `str(quantity)` slightly nicer.
if sys.version_info[0] == 3:
    units.default_format = 'P~'
else:
    # NOTE: 'P' outputs non-ascii unicode symbols and therefore breaks
    # str(quantity) on python2 (UnicodeEncodeError).
    units.default_format = '~'


# extent unit registry.
# NOTE: parsing %, ‰ doesn't work automatically yet in pint.
units.define(u'ratio = []')
units.define(u'percent = 0.01 ratio = %')
units.define(u'permille = 0.001 ratio = ‰')


def strip_unit(quantity, unit=None):
    """Convert the quantity to a plain float."""
    if unit is None:
        return quantity.magnitude
    return quantity.to(unit).magnitude


def tounit(quantity, unit):
    """Cast the quantity to a specific unit."""
    return quantity.to(unit)


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
    unit = unicode(unit)
    # as of pint-0.6 the following symbols fail to be parsed on python2:
    unit = unit.replace(u'µ', u'micro')
    unit = unit.replace(u'%', u'percent')
    unit = unit.replace(u'‰', u'permille')
    return units(unit)


def from_config_dict(conf_dict):
    """Convert a config dict of units to their in-memory representation."""
    return {k: from_config(v) for k,v in conf_dict.items()}


class UnitConverter(object):

    """
    Quantity converter.

    Used to add and remove units from quanitities and evaluate expressions.

    :ivar dict _units: unit dictionary
    """

    def __init__(self, units):
        """Store Madx instance for later use."""
        self._units = dicti(units)

    def get_unit_label(self, name):
        """Get the name of the unit for the specified parameter name."""
        units = self._units
        return get_unit_label(units[name]) if name in units else ''

    def add_unit(self, name, value):
        """Add units to a single number."""
        units = self._units
        if name in units:
            if isinstance(value, Expression):
                return SymbolicValue(value.expr, value.value, units[name])
            else:
                return units[name] * value
        else:
            return value

    def strip_unit(self, name, value):
        """Convert to madx units."""
        units = self._units
        return strip_unit(value, units[name]) if name in units else value

    def dict_add_unit(self, obj):
        """Add units to all elements in a dictionary."""
        return obj.__class__({k: self.add_unit(k, obj[k]) for k in obj})

    def dict_strip_unit(self, obj):
        """Remove units from all elements in a dictionary."""
        return obj.__class__({k: self.strip_unit(k, obj[k]) for k in obj})
