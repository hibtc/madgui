# encoding: utf-8
"""
MadX string expression that can automatically evaluate to a float.
"""

# force new style imports
from __future__ import absolute_import

# exported symbols
__all__ = ['SymbolicValue']


class SymbolicValue(object):

    """
    Representation of a symbolic MADX expression.

    Needs to be evaluated via model.evaluate.
    """

    def __init__(self, madx_instance, expression, unit):
        """Store model, expression and unit as instance variables."""
        self._madx_instance = madx_instance
        self._expression = expression
        self._unit = unit

    def __float__(self):
        """Evaluate expression and return as pure float in the base unit."""
        return self.asNumber()

    def __str__(self):
        """Evaluate expression and return with associated unit."""
        return str(self._evaluate())

    def __repr__(self):
        """Return representation without evaluating the expression."""
        return "%s(%r)" % (self.__class__.__name__, self._expression)

    def _evaluate(self):
        return self._unit * self._madx_instance.evaluate(self._expression)

    def asNumber(self, unit=None):
        """Evaluate expression and return as pure float."""
        return self._evaluate().asNumber(unit)

    def asUnit(self, unit=None):
        """Evaluate expression and cast to the specified unit."""
        return self._evaluate().asUnit(unit)

    def strUnit(self):
        """Return a string that describes the unit."""
        return self._unit.strUnit()
