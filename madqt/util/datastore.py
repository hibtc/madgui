
from abc import abstractmethod


class DataStore(object):

    """
    Base class that defines the protocol between data source/sink and
    ParamTable.
    """

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
