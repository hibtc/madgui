"""
Provides unit conversion.
"""
__all__ = ['units', 'stripunit', 'tounit', 'unit_label']

from unum import units
from pydicti import dicti

def stripunit(quantity, unit=None):
    return quantity.asNumber(unit)

def tounit(quantity, unit):
    return quantity.asUnit(unit)

def unit_label(quantity):
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

