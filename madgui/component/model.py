# encoding: utf-8
"""
Simulator component for the MadGUI application.
"""

# force new style imports
from __future__ import absolute_import

# standard library
import os
import subprocess
import sys

# 3rd party
from cpymad.madx import Madx, CommandLog
from cpymad import _rpc

# internal
from madgui.core.plugin import HookCollection

# exported symbols
__all__ = [
    'Simulator',
    'Segment',
]


class Simulator(object):

    """
    Contains the whole global state of a MAD-X instance and (possibly) loaded
    metadata.

    :ivar Madx madx: MAD-X interpreter instance
    :ivar Model model: associated metadata or None
    :ivar list simulations: active simulations
    """

    def __init__(self, utool):
        """Initialize with (Madx, Model)."""

        # stdin=None leads to an error on windows when STDIN is broken.
        # therefore, we need use stdin=os.devnull:
        with open(os.devnull, 'r') as devnull:
            client, process = _rpc.LibMadxClient.spawn_subprocess(
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=devnull,
                bufsize=0)
        self.rpc_client = client
        self.remote_process = process
        self.libmadx = client.libmadx
        self.madx = Madx(libmadx=self.libmadx,
                         command_log=CommandLog(sys.stdout))

        self.model = None
        self.utool = utool
        self.simulations = []


class Segment(object):

    """
    Simulate one fixed segment, i.e. sequence + range.

    :ivar Madx madx:
    :ivar list elements:
    :ivar dict twiss_args:
    """

    # TODO: separate into multipble components:
    #
    # - MadX
    # - metadata (cpymad.model?)
    # - Sequence (elements)
    # - Matcher
    #
    # The MadX instance should be connected to a specific frame at
    # construction time and log all output there in two separate places
    # (panels?):
    #   - logging.XXX
    #   - MAD-X library output
    #
    # Some properties (like `elements` in particular) can not be determined
    # at construction time and must be retrieved later on. Generally,
    # `elements` can come from two sources:
    # - MAD-X memory
    # - metadata
    # A reasonable mechanism is needed to resolve/update it.

    # TODO: more logging
    # TODO: automatically switch directories when CALLing files

    def __init__(self,
                 sequence,
                 range,
                 madx,
                 utool,
                 name=None,
                 twiss_args=None):
        """
        """
        self.hook = HookCollection(
            show='madgui.component.model.show',
            update=None)

        self._sequence = sequence
        self.range = range
        self.madx = madx
        self.utool = utool
        self.name = name
        self.twiss_args = twiss_args
        self._columns = ['name', 'l', 'angle', 'k1l',
                         's',
                         'x', 'y',
                         'betx','bety']
        self._update_elements()
        self.twiss()

    @property
    def beam(self):
        """Get the beam parameter dictionary."""
        beam = self.madx.get_sequence(self.name).beam
        return self.utool.dict_add_unit(beam)

    @beam.setter
    def beam(self):
        """Set beam from a parameter dictionary."""

    def element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        if pos is None:
            return None
        for elem in self.elements:
            at, L = elem['at'], elem['l']
            if pos >= at and pos <= at+L:
                return elem
        return None

    def element_by_name(self, name):
        """Find the element in the sequence list by its name."""
        for elem in self.elements:
            if elem['name'].lower() == name.lower():
                return elem
        return None

    def twiss(self):
        """Recalculate TWISS parameters."""
        twiss_args = self.utool.dict_strip_unit(self.twiss_args)
        results = self.madx.twiss(sequence=self.sequence.name,
                                  range=self.range,
                                  columns=self._columns,
                                  twiss_init=twiss_args)
        self._update_twiss(results)

    def _update_twiss(self, results):
        """Update TWISS results."""
        data = results.copy()
        self.tw = self.utool.dict_add_unit(data)
        self.summary = self.utool.dict_add_unit(results.summary)
        self.update()

    @property
    def sequence(self):
        return self.madx.sequences[self._sequence]

    def _update_elements(self):
        raw_elements = self.sequence.elements
        self.elements = list(map(self.utool.dict_add_unit, raw_elements))

    def element_index_by_name(self, name):
        """Find the element index in the twiss array by its name."""
        return self.sequence.elements.index(name)

    def get_element_index(self, elem):
        """Get element index by it name."""
        return self.element_index_by_name(elem['name'])

    def get_twiss(self, elem, name):
        """Return beam envelope at element."""
        return self.tw[name][self.get_element_index(elem)]

    def update(self):
        """Perform post processing."""
        # data post processing
        self.pos = self.tw['s']
        self.tw['envx'] = (self.tw['betx'] * self.summary['ex'])**0.5
        self.tw['envy'] = (self.tw['bety'] * self.summary['ey'])**0.5
        # Create aliases for x,y that have non-empty common prefix. The goal
        # is to make the config file entries less awkward that hold this
        # prefix:
        self.tw['posx'] = self.tw['x']
        self.tw['posy'] = self.tw['y']
        self.hook.update()

    def evaluate(self, expr):
        """Evaluate a MADX expression and return the result as float."""
        return self.madx.evaluate(expr)

