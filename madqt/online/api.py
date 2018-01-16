"""
This module defines the API of any online control plugin. Note that the API
is subject to change (as is most parts of madqt…).

The interface contract is currently designed as follows:

    - A subclass of :class:`PluginLoader` is registered under the
      "madqt.online.PluginLoader" entry point.

    - It loads the DLL / connects the database when requested and returns a
      :class:`OnlinePlugin` instance.

    - An :class:`OnlinePlugin` instance is used to instanciate accessors for
      the actual elements.

    - There are two kinds of accessors (returned as tuple):

        - :class:`ElementBackend` performs the actual database I/O, i.e.
          reads/writes parameters from the database.

        - :class:`ElementBackendConverter` performs parameter conversions
          between internal and standard representation
"""

from abc import ABCMeta, abstractmethod, abstractproperty

_Interface = ABCMeta('_Interface', (object,), {})


class UnknownElement(Exception):
    pass


class PluginLoader(_Interface):

    """Loader interface for online control plugin."""

    @classmethod
    def check_avail(self):
        """Check if the plugin is available."""
        return True

    @classmethod
    def load(self, frame):
        """Get a :class:`OnlinePlugin` instance."""
        raise NotImplementedError


class OnlinePlugin(_Interface):

    """Interface for a connected online control plugin."""

    @abstractmethod
    def connect(self):
        """Connect the online plugin to the control system."""

    @abstractmethod
    def disconnect(self):
        """Unload the online plugin, free resources."""

    @abstractmethod
    def execute(self):
        """Commit transaction."""

    @abstractmethod
    def param_info(self, segment, element, key):
        """Get parameter info for backend key."""

    @abstractmethod
    def get_monitor(self, segment, elements):
        """
        Get a (:class:`ElementBackendConverter`, :class:`ElementBackend`)
        tuple for a monitor.
        """

    @abstractmethod
    def get_dipole(self, segment, elements, skew):
        """
        Get a (:class:`ElementBackendConverter`, :class:`ElementBackend`)
        tuple for a dipole.
        """

    @abstractmethod
    def get_quadrupole(self, segment, elements):
        """
        Get a (:class:`ElementBackendConverter`, :class:`ElementBackend`)
        tuple for a quadrupole.
        """

    @abstractmethod
    def get_solenoid(self, segment, elements):
        """
        Get a (:class:`ElementBackendConverter`, :class:`ElementBackend`)
        tuple for a solenoid.
        """

    @abstractmethod
    def get_kicker(self, segment, elements, skew):
        """
        Get a (:class:`ElementBackendConverter`, :class:`ElementBackend`)
        tuple for a kicker.
        """


class ElementBackend(_Interface):

    """Mitigates r/w access to the parameters of an element."""

    @abstractmethod
    def get(self):
        """Get dict of values (in backend representation)."""

    @abstractmethod
    def set(self, values):
        """Set dict of values (must be in backend representation)."""


class ElementBackendConverter(_Interface):

    """
    Converts element parameters from standard representation to internal
    representation for some backend (and vice versa).
    """

    @abstractproperty
    def standard_keys(self):
        """List of properties in standard representation."""

    def backend_keys(self):
        """List of properties in backend (DB) representation."""
        raise NotImplementedError

    @abstractmethod
    def to_backend(self, values):
        """Convert values backend (DB) representation."""

    @abstractmethod
    def to_standard(self):
        """Convert values standard representation."""


def _key_transform(values, keys_from, keys_to):
    """
    Transform keys in ``values`` by replacing keys in ``keys_from`` by
    the key in ``keys_to`` with the same index.
    """
    tr = {a: b for a, b in zip(keys_from, keys_to)}
    return {tr[key]: val for key, val in values.items()}


class NoConversion(ElementBackendConverter):

    """
    Special case of :class:`ElementBackendConverter` that does no conversion
    except for parameter renaming.
    """

    def to_standard(self, values):
        return _key_transform(values, self.backend_keys, self.standard_keys)

    def to_backend(self, values):
        return _key_transform(values, self.standard_keys, self.backend_keys)
