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
class Enum(object):

    def __init__(self, value):
        if value not in self._values:
            raise ValueError("{} does not allow value {!r}\nOnly: {}"
                             .format(self.__class__, value, self._values))
        self.value = value

    def __str__(self):
        return self.value

    def __repr__(self):
        return '<enum {!r} = {!r}>'.format(self.__class__.__name__, self.value)

    def __format__(self, spec):
        return self.value


def make_enum(name, values):
    return EnumMeta(str(name), (Enum,), {'_values': tuple(values)})
