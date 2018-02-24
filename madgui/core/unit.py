"""
Provides unit conversion.
"""

from pkg_resources import resource_filename

import numpy as np
import pint

from madgui.util.symbol import SymbolicValue
from madgui.util.defaultdict import DefaultDict

from cpymad.types import Expression


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
    'UnitConverter',
]


def initialize():
    # Make sure 'constants_en.txt' exists as well (it is imported by
    # 'default_en.txt'):
    # TODO: use consts?
    units_spec = resource_filename('madgui.data', 'default_en.txt')
    units = pint.UnitRegistry(units_spec)

    # make `str(quantity)` slightly nicer
    units.default_format = 'P~'

    # extend unit registry
    # NOTE: parsing %, ‰ doesn't work automatically yet in pint.
    units.define('ratio = []')
    units.define('percent = 0.01 ratio = %')
    units.define('permille = 0.001 ratio = ‰')
    return units


units = initialize()
number_types = (int, float, units.Quantity, SymbolicValue, Expression)


def isclose(q1, q2):
    m1 = strip_unit(q1, get_unit(q1))
    m2 = strip_unit(q2, get_unit(q1))
    return np.isclose(m1, m2)


def allclose(q1, q2):
    return all(isclose(a, b) for a, b in zip(q1, q2))


def get_unit(quantity):
    if isinstance(quantity, units.Quantity):
        return units.Quantity(1, quantity.units)
    if isinstance(quantity, SymbolicValue):
        return units.Quantity(1, quantity._unit)
    return None


def add_unit(quantity, unit):
    if quantity is None or unit is None:
        return quantity
    if isinstance(quantity, units.Quantity):
        return quantity.to(toquantity(unit))
    return quantity * unit


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
    if quantity is None:
        return ''
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
         for key, value in quantity.units._units.items()})
    as_ratio = any(exp > 0 for _, exp in short.items())
    return pint.formatting.formatter(
        short.items(),
        as_ratio=as_ratio,
        single_denominator=True,
        product_fmt='·',
        division_fmt='/',
        power_fmt='{0}{1}',
        parentheses_fmt='({0})',
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
        return None
    if isinstance(unit, list):
        return [from_config(u) for u in unit]
    if isinstance(unit, bytes):
        unit = unit.decode('utf-8')
    unit = '{}'.format(unit)
    # as of pint-0.8.1 the following symbols fail to be parsed:
    unit = unit.replace('%', 'percent')
    unit = unit.replace('‰', 'permille')
    return units(unit)


class UnitConverter:

    """
    Quantity converter.

    Used to add and remove units from quanitities and evaluate expressions.

    :ivar dict _units: unit dictionary
    """

    def __init__(self, units):
        self._units = units

    @classmethod
    def from_config_dict(cls, conf_dict):
        """Convert a config dict of units to their in-memory representation."""
        return cls(DefaultDict(lambda k: from_config(conf_dict[k.lower()])))

    def get_unit_label(self, name):
        """Get the name of the unit for the specified parameter name."""
        return get_unit_label(self._units.get(name))

    def add_unit(self, name, value):
        """Add units to a single number."""
        unit = self._units.get(name)
        if unit:
            if isinstance(value, (list, tuple)):
                # FIXME: 'zip' truncates without warning if not enough units
                # are defined
                return [self._add_unit(v, u)
                        for v, u in zip(value, unit)]
            return self._add_unit(value, unit)
        else:
            return value

    def _add_unit(self, value, unit):
        if isinstance(value, Expression):
            return SymbolicValue(value.expr, value.value, unit)
        elif isinstance(unit, list):
            return [self._add_unit(v, u) for v, u in zip(value, unit)]
        else:
            return unit * value

    def strip_unit(self, name, value):
        """Convert to MAD-X units."""
        return strip_unit(value, self._units.get(name))

    def dict_add_unit(self, obj):
        """Add units to all elements in a dictionary."""
        return obj.__class__((k, self.add_unit(k, obj[k])) for k in obj)

    def dict_strip_unit(self, obj):
        """Remove units from all elements in a dictionary."""
        return obj.__class__((k, self.strip_unit(k, obj[k])) for k in obj)

    def normalize_unit(self, name, value):
        """Normalize unit to unit used in MAD-X."""
        unit = self._units.get(name)
        if unit:
            if not isinstance(value, Expression):
                return tounit(value, unit)
        return value

    def dict_normalize_unit(self, obj):
        """Normalize unit for all elements in a dictionary."""
        return obj.__class__((k, self.normalize_unit(k, obj[k])) for k in obj)
