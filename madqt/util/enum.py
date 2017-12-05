"""
Simple enum type.
"""


# Metaclass for creating enum classes:
class EnumMeta(type):

    def __str__(self):
        return '<enum {!r}>'.format(self.__name__)

    __repr__ = __str__

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)


# Enum base class
class Enum:

    def __init__(self, value):
        preset = value.lower() in self._lower
        if not preset and self._strict:
            raise ValueError("{} does not allow value {!r}\nOnly: {}"
                             .format(self.__class__, value, self._values))
        self.value = self._lower[value.lower()] if preset else value

    def __str__(self):
        return self.value

    def __repr__(self):
        return '<enum {!r} = {!r}>'.format(self.__class__.__name__, self.value)

    def __format__(self, spec):
        return self.value


def make_enum(name, values, strict=True):
    values = tuple(values)
    return EnumMeta(str(name), (Enum,), {
        '_values': values,
        '_lower': {v.lower(): v for v in values},
        '_strict': strict,
    })
