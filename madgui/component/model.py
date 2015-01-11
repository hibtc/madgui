# encoding: utf-8
"""
Simulator component for the MadGUI application.
"""

# force new style imports
from __future__ import absolute_import

# standard library
from collections import namedtuple
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

    # TODO: more logging
    # TODO: automatically switch directories when CALLing files?

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
        self.madx = Madx(libmadx=self.libmadx)

        self.model = None
        self.utool = utool
        self.simulations = []


ElementInfo = namedtuple('ElementInfo', ['name', 'index', 'at'])


class SegmentedRange(object):

    """
    Displayed range.

    :ivar dict segments: segments
    :ivar dict twiss_initial: initial conditions
    """

    def __init__(self, simulator, sequence, range='#s/#e'):
        """
        :param Simulator simulator:
        :param str sequence:
        :param tuple range:
        """
        self.hook = HookCollection(
            update='madgui.component.manager.update',
            add_segment='madgui.component.manager.add_segment',
        )
        self.simulator = simulator
        self.sequence = simulator.madx.sequences[sequence]
        self.range = range
        # TODO: use range
        self.start, self.stop = self.parse_range(range)
        self.segments = {}
        self.twiss_initial = {}
        # TODO ..
        raw_elements = self.sequence.elements
        self.elements = list(map(
            self.simulator.utool.dict_add_unit, raw_elements))

    def get_element_info(self, element):
        """Get :class:`ElementInfo` from element name or index."""
        if isinstance(element, ElementInfo):
            return element
        if element == '#s':
            element = 0
        elif element == '#e':
            element = -1
        elif isinstance(element, (basestring, dict)):
            element = self.sequence.elements.index(element)
        element_data = self.simulator.utool.dict_add_unit(
            self.sequence.elements[element])
        return ElementInfo(element_data['name'], element, element_data['at'])

    def parse_range(self, range):
        """Convert a range str/tuple to a tuple of :class:`ElementInfo`."""
        if isinstance(range, basestring):
            range = range.split('/')
        start_name, stop_name = range
        return (self.get_element_info(start_name),
                self.get_element_info(stop_name))

    # segment allocation

    def set_twiss_initial(self, element, twiss_args):
        """
        Set initial conditions at specified element.

        If there are currently no initial conditions associated with the
        element, they are added and the enclosing segment is split in two.
        """
        self.twiss_initial[element.index] = twiss_args
        segments = self.segments
        if element.index in segments:
            segments[element.index].twiss()
        else:
            try:
                prev_start = max(i for i in segments if i < element.index)
            except ValueError:
                # no previous segment
                self._create_segment(
                    self.start,
                    min(segments) if segments else self.stop)
            else:
                # split previous segment
                old_seg = self._remove_segment(prev_start)
                front_seg = self._create_segment(old_seg.start, element)
                self._create_segment(element, old_seg.stop)
        self.hook.update()

    def _create_segment(self, start, stop):
        segment = Segment(self.sequence,
                          self.get_element_info(start),
                          self.get_element_info(stop),
                          self.simulator.madx,
                          self.simulator.utool,
                          self.twiss_initial[start.index])
        self.segments[start.index] = segment
        segment.twiss()
        self.hook.add_segment(segment)
        return segment

    def _remove_segment(self, start_index):
        segment = self.segments.pop(start_index)
        old_seg.hook.remove()
        return segment

    def remove_twiss_inital(self, element):
        """
        Remove initial conditions at specified element.

        If the initial conditions can be removed, the two adjacent segments
        are merged into one.
        """
        del self.twiss_initial[element.index]
        del_seg = self._remove_segment(element.index)
        try:
            prev_start = max(i for i in segments if i < element.index)
        except ValueError:
            pass
        else:
            prev_seg = self._remove_segment(prev_start)
            self._create_segment(prev_seg.start, del_seg.stop)
        self.hook.update()

    def get_segment_at(self, at):
        """Get the segment at specified S coordinate."""
        for segment in self.segments.values():
            if segment.start.at <= at and segment.stop.at >= at:
                return segment
        return None

    @property
    def beam(self):
        """Get the beam parameter dictionary."""
        return self.simulator.utool.dict_add_unit(self.sequence.beam)

    @beam.setter
    def beam(self, beam):
        """Set beam from a parameter dictionary."""
        self.madx.command.beam(**self.simulator.utool.dict_strip_unit(beam))
        # TODO: re-run twiss

    def element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        if pos is None:
            return None
        for elem in self.elements:
            at, L = elem['at'], elem['l']
            if pos >= at and pos <= at+L:
                return elem
        return None

    def get_element_index(self, elem):
        """Get element index by it name."""
        return self.sequence.elements.index(elem)

    def get_segment(self, element):
        element = self.get_element_info(element)
        index = max(i for i in self.segments if i <= element.index)
        return self.segments[index]

    def get_twiss(self, elem, name):
        """Return beam envelope at element."""
        element = self.get_element_info(elem)
        segment = self.get_segment(element)
        return segment.tw[name][element.index - segment.start.index]


class Segment(object):

    """
    Simulate one fixed segment, i.e. sequence + range.

    :ivar Madx madx:
    :ivar list elements:
    :ivar dict twiss_args:
    """

    # TODO: adjust for S-offset

    def __init__(self, sequence, start, stop, madx, utool, twiss_args):
        """
        """
        self.hook = HookCollection(
            update=None,
            remove=None)
        self.sequence = sequence
        self.start = start
        self.stop = stop
        self.range = (start.name, stop.name)
        self.madx = madx
        self.utool = utool
        self.twiss_args = twiss_args
        self._columns = ['name', 'l', 'angle', 'k1l',
                         's',
                         'x', 'y',
                         'betx','bety']

    def twiss(self):
        """Recalculate TWISS parameters."""
        twiss_args = self.utool.dict_strip_unit(self.twiss_args)
        results = self.madx.twiss(sequence=self.sequence.name,
                                  range=self.range,
                                  columns=self._columns,
                                  twiss_init=twiss_args)
        # Update TWISS results
        self.tw = self.utool.dict_add_unit(results)
        self.summary = self.utool.dict_add_unit(results.summary)
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
