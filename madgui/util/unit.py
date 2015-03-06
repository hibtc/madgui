# encoding: utf-8
"""
Provides unit conversion.
"""

# force new style imports
from __future__ import absolute_import

# 3rd party
from pint import UnitRegistry
from pint.unit import UnitsContainer
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


units = UnitRegistry()


# compatibility
try:                    # python2
    basestring
except NameError:       # python3 (let's think about future...)
    basestring = str


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


def get_raw_label(quantity):
    """Get the name of the unit, without enclosing brackets."""
    short = UnitsContainer({units._get_symbol(key): value
                            for key, value in quantity.units.items()})
    return u'{:P}'.format(short)


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
    unit = str(unit)
    unit.replace(u'µ', u'micro')
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
