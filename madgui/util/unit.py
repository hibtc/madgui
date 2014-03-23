"""
Provides unit conversion.
"""

# force new style imports
from __future__ import absolute_import

# 3rd party
from unum import units
from pydicti import dicti

# exported symbols
__all__ = ['units',
           'stripunit',
           'tounit',
           'unit_label',
           'madx']


def stripunit(quantity, unit=None):
    """Convert the quantity to a plain float."""
    return quantity.asNumber(unit)


def tounit(quantity, unit):
    """Cast the quantity to a specific unit."""
    return quantity.asUnit(unit)


def unit_label(quantity):
    """Get name of the unit."""
    return quantity.strUnit()


madx = dicti({
    'L': units.m,
    'lrad': units.m,
    'at': units.m,
    's': units.m,
    'betx': units.m,
    'bety': units.m,
    'angle': units.rad,
    'k1': units.m**-2,
    'k1l': units.m**-2,
    'ex': units.m,
    'ey': units.m,
    'tilt': units.rad,
    'hgap': units.m,
    'h': units.rad/units.m,
    'fint': 1,            # dimenisonless
    'fintx': 1,           # dimenisonless
    'e1': units.rad,
    'e2': units.rad,
    # 'knl': None,            # varying units
    # 'ksl': None,            # varying units
    # 'vary': None,           # should be removed
})
