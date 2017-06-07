from __future__ import absolute_import

from abc import abstractmethod
from collections import OrderedDict


# TODO: datastores should have labels

class DataStore(object):

    """
    Base class that defines the protocol between data source/sink and
    ParamTable.
    """

    label = None

    @abstractmethod
    def get(self):
        """Get a dictionary with all values."""

    @abstractmethod
    def update(self, values):
        """Update values from dictionary."""

    @abstractmethod
    def mutable(self, key):
        """Check whether the parameter belonging to a certain key is mutable."""

    @abstractmethod
    def default(self, key):
        """Get default value for the given key."""


class SuperStore(DataStore):

    """DataStore that is composed of substores."""

    def __init__(self, substores):
        self.substores = substores

    def get(self):
        """Get a dictionary with all values."""
        return OrderedDict([
            (key, ds.get())
            for key, ds in self.substores.items()
        ])

    def update(self, values):
        """Update values from dictionary."""
        for key, vals in values.items():
            self.substores[key].update(vals)
