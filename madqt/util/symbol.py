"""
MAD-X string expression that can automatically evaluate to a float.
"""

__all__ = [
    'SymbolicValue',
]


class SymbolicValue:

    """
    Representation of a symbolic MAD-X expression with a unit.

    Needs to be evaluated via model.evaluate.
    """

    def __init__(self, expression, value, unit):
        """Store model, expression and unit as instance variables."""
        self._expression = expression
        self._value = value
        self._unit = unit

    def __float__(self):
        """Evaluate expression and return as pure float in the base unit."""
        return self._value

    def __str__(self):
        """Evaluate expression and return with associated unit."""
        return str(self._get())

    def __repr__(self):
        """Return representation without evaluating the expression."""
        return "%s(%r)" % (self.__class__.__name__, self._expression)

    def _get(self):
        return self._unit * self._value

    @property
    def value(self):
        return self._get()

    # TODO: need magnitude etc

    @property
    def magnitude(self):
        """Evaluate expression and return as pure float."""
        return self._value

    @property
    def units(self):
        """Return a string that describes the unit."""
        return self._unit.units

    def to(self, other):
        return self._get().to(other)
