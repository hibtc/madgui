"""
This module defines the API of any online control plugin. Note that the API
is subject to change (as is most parts of madgui…).

The user must add their derived :class:`Backend` to the madgui config as:

.. code-block:: yaml

    online_control:
      backend: 'hit_acs.plugin:HitACS'
"""

__all__ = [
    'Backend',
    'ParamInfo',
]

from abc import ABCMeta, abstractmethod
from collections import namedtuple


class Backend(metaclass=ABCMeta):

    """Interface for a online control plugin."""

    @abstractmethod
    def __init__(self, session, settings):
        """Get a :class:`Backend` instance."""
        raise NotImplementedError

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
    def param_info(self, knob):
        """Get parameter info for backend key."""

    @abstractmethod
    def read_monitor(self, name):
        """
        Read out one monitor, return values as dict with keys:

            widthx:     Beam x width
            widthy:     Beam y width
            posx:       Beam x position
            posy:       Beam y position
        """

    @abstractmethod
    def read_param(self, param):
        """Read parameter. Return numeric value."""

    @abstractmethod
    def write_param(self, param, value):
        """Update parameter into control system."""

    @abstractmethod
    def get_beam(self):
        """
        Return a dict ``{name: value}`` for all beam properties, in MAD-X
        units. At least: particle, mass, charge, energy
        """


ParamInfo = namedtuple('ParamInfo', [
    'name',
    'ui_name',
    'ui_hint',
    'ui_prec',
    'unit',
    'ui_unit',
    'ui_conv',
])
