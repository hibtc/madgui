# encoding: utf-8
"""
Core components for a very simple plugin system.

Short class overview:

- :func:`Hook` should be used for all named events (plugins).

- :class:`Multicast` is an abstract base class. It only contains mixins and
  is missing the vital attribute ``slots``

- :class:`List` represents a set of event handlers that are manageable from
  within your application.

- :class:`EntryPoint` multicasts events to setuptools entry points.
"""

from __future__ import absolute_import

__all__ = ['Hook',
           'Multicast',
           'List',
           'EntryPoint']

import pkg_resources


def Hook(name):
    """
    Return a plugin hook with the given name.

    Currently, a plugin hook is basically a globally named signal, i.e. a
    :class:`List` object with an :class:`EntryPoint` object as its first
    client. In the future, a folder based detection mechanism may be added.

    This is the conventional function to use in MadGUI for plugins.

    Note, that the list of dynamically connected clients is not and mustn't
    be a global state! There may be multiple instances being able to add or
    remove clients independently.
    """
    return List([EntryPoint(name)])


def hookproperty(name, doc=""):
    """Return a property that associates a Hook to each instance."""
    def signal(self):
        try:
            return self._events[name]
        except AttributeError:
            self._events = {}
        except KeyError:
            pass
        hook = self._events[name] = Hook(name)
        return hook
    return property(signal, doc=doc or "Hook for {}".format(name))


def _freeze(slot):
    """Return a frozen version of a single slot."""
    try:
        slots = slot.freeze
    except AttributeError:
        return slot
    else:
        return freeze()


class Multicast(object):

    """
    Signal base class.

    Signals are responsible for multiplexing events to several clients.
    Events can simply be understood as multicast function calls.

    This is an abstract base class. Concretizations need to supply the
    attribute :ivar:`slots`.
    """

    def _reduce(self, iterable):
        """Default reduce mechanism: use the very last result or ``None``."""
        result = None
        for result in iterable:
            pass
        return result

    def _map(self, *args, **kwargs):
        """Return an iterable that calls the slots when iterated over."""
        return (slot(*args, **kwargs) for slot in self.slots)

    def __call__(self, *args, **kwargs):
        """Call all slots and return reduced result."""
        return self._reduce(self._map(*args, **kwargs))

    def freeze(self):
        """Return new signal with all connected slots."""
        return List([_freeze(slot) for slot in self.slots])


class List(Multicast):

    """
    Signal connected to dynamic list of event handlers.

    Use this class if the list of event handlers needs to be dynamically
    managed from within the application.
    """

    def __init__(self, slots=None):
        """Initialize with an externally created list of slots."""
        if slots is not None:
            self._slots = slots

    @property
    def slots(self):
        """Return an iterable over all event handlers."""
        try:
            return self._slots
        except AttributeError:
            slots = self._slots = []
            return slots

    def connect(self, slot):
        """Register an event handler."""
        return self.slots.add(slot)

    def disconnect(self, slot):
        """Remove an event handler."""
        self.slots.disconnect(slot)


def iter_entry_points(group, name=None):
    """Return an iterable over all relevant entry points."""
    for ep in pkg_resources.iter_entry_points(group, name):
        yield ep.load()


class EntryPoint(Multicast):

    """
    Signal connected to setuptools entry points.

    Instances of this class are used to dynamically discover and invoke
    event handlers that are installed as setuptools entry points.
    """

    def __init__(self, group, name=None):
        """Set the entry point group and, optionally, implementation name."""
        self._group = group
        self._name = name

    @property
    def slots(self):
        """Return an iterable over all relevant entry points."""
        return iter_entry_points(self._group, self._name)
