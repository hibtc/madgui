# encoding: utf-8
"""
Session component for the MadGUI application.
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
from cpymad.util import normalize_range_name
from cpymad import _rpc

# internal
from madgui.core.plugin import HookCollection

# exported symbols
__all__ = [
    'ElementInfo',
    'SegmentedRange',
    'Session',
    'Segment',
]


class Session(object):

    """
    Contains the whole global state of a MAD-X instance and (possibly) loaded
    metadata.

    :ivar Madx madx: MAD-X interpreter instance
    :ivar Model model: associated metadata or None
    """

    # TODO: more logging
    # TODO: automatically switch directories when CALLing files?
    # TODO: saveable state

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
        self.segman = None


ElementInfo = namedtuple('ElementInfo', ['name', 'index', 'at'])


class SegmentedRange(object):

    """
    Displayed range.

    :ivar dict segments: segments
    :ivar dict twiss_initial: initial conditions
    """

    def __init__(self, session, sequence, range='#s/#e'):
        """
        :param Session session:
        :param str sequence:
        :param tuple range:
        """
        self.hook = HookCollection(
            update='madgui.component.manager.update',
            add_segment='madgui.component.manager.add_segment',
        )
        self.session = session
        self.sequence = session.madx.sequences[sequence]
        self.range = range
        self.start, self.stop = self.parse_range(range)
        self.segments = {}
        self.twiss_initial = {}
        raw_elements = self.sequence.elements
        self.elements = list(map(
            self.session.utool.dict_add_unit, raw_elements))

    def get_element_info(self, element):
        """Get :class:`ElementInfo` from element name or index."""
        if isinstance(element, ElementInfo):
            return element
        if isinstance(element, (basestring, dict)):
            element = self.sequence.elements.index(element)
        element_data = self.session.utool.dict_add_unit(
            self.sequence.elements[element])
        if element < 0:
            element += len(self.sequence.elements)
        return ElementInfo(element_data['name'], element, element_data['at'])

    def parse_range(self, range):
        """Convert a range str/tuple to a tuple of :class:`ElementInfo`."""
        if isinstance(range, basestring):
            range = range.split('/')
        start_name, stop_name = range
        return (self.get_element_info(start_name),
                self.get_element_info(stop_name))

    # segment allocation

    def set_all(self, data):
        edges = sorted(data) + [self.stop.index]
        new_segments = list(zip(edges[:-1], edges[1:]))
        old_twiss = self.twiss_initial
        self.twiss_initial = data
        # remove obsolete segments
        for seg in self.segments.values():
            if (seg.start.index, seg.stop.index) not in new_segments:
                self._remove_segment(seg.start.index)
        # insert new segments / update initial conditions
        for start, stop in new_segments:
            try:
                seg = self.segments[start]
            except KeyError:
                self._create_segment(start, stop)
            else:
                seg.twiss_args = data[start]
                seg.twiss()
        self.hook.update()

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
        start = self.get_element_info(start)
        stop = self.get_element_info(stop)
        segment = Segment(self.sequence,
                          start,
                          stop,
                          self,
                          self.twiss_initial[start.index])
        self.segments[start.index] = segment
        segment.twiss()
        self.hook.add_segment(segment)
        return segment

    def _remove_segment(self, start_index):
        segment = self.segments.pop(start_index)
        segment.hook.remove()
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
        return self.session.utool.dict_add_unit(self.sequence.beam)

    @beam.setter
    def beam(self, beam):
        """Set beam from a parameter dictionary."""
        self.session.madx.command.beam(
            **self.session.utool.dict_strip_unit(beam))
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
        return next((segment for segment in self.segments.values()
                     if segment.contains(element)),
                    None)

    def get_twiss(self, elem, name):
        """Return beam envelope at element."""
        element = self.get_element_info(elem)
        segment = self.get_segment(element)
        if segment is None:
            return None
        return segment.tw[name][element.index - segment.start.index]


def dict_setdefault(a, b):
    for k, v in b.items():
        a.setdefault(k, v)
    return a


class Segment(object):

    """
    Simulate one fixed segment, i.e. sequence + range.

    :ivar Madx madx:
    :ivar list elements:
    :ivar dict twiss_args:
    """

    _columns = [
        'name', 'l', 'angle', 'k1l',
        's',
        'x', 'y',
        'betx','bety',
        'alfx', 'alfy',
    ]

    # TODO: extend list of merge-columns
    _mixin_columns = [
        'x', 'y',
        'betx','bety',
        'alfx', 'alfy',
    ]

    def __init__(self, sequence, start, stop, segman, twiss_args):
        """
        """
        self.hook = HookCollection(
            update=None,
            remove=None)
        self.sequence = sequence
        self.start = start
        self.stop = stop
        self.range = (normalize_range_name(start.name),
                      normalize_range_name(stop.name))
        self.segman = segman
        self.madx = segman.session.madx
        self.utool = segman.session.utool
        self.twiss_args = twiss_args
        self.segman = segman

    @property
    def mixin_twiss_args(self):
        # NOTE: this procedure currently causes a "jump" in the TWISS data at
        # the boundary element. I guess MAD-X returns the TWISS values at the
        # center of the element, which can therefore not be used as initial
        # conditions at the start of the element.
        twiss_args = self.twiss_args
        if not twiss_args.get('mixin'):
            return twiss_args
        twiss_args = twiss_args.copy()
        del twiss_args['mixin']
        if self.start.index > 0:
            precede_seg = self.segman.get_segment(self.start.index - 1)
            if precede_seg is not None:
                precede_tw = {col: precede_seg.tw[col][-1]
                              for col in self._mixin_columns}
                dict_setdefault(twiss_args, precede_tw)
        return twiss_args

    def contains(self, element):
        return (self.start.index <= element.index and
                self.stop.index >= element.index)

    def twiss(self):
        """Recalculate TWISS parameters."""
        twiss_args = self.utool.dict_strip_unit(self.mixin_twiss_args)
        results = self.madx.twiss(sequence=self.sequence.name,
                                  range=self.range,
                                  columns=self._columns,
                                  twiss_init=twiss_args)
        # Update TWISS results
        self.tw = self.utool.dict_add_unit(results)
        self.summary = self.utool.dict_add_unit(results.summary)
        # data post processing
        self.tw['s'] += self.start.at
        self.pos = self.tw['s']
        self.tw['envx'] = (self.tw['betx'] * self.summary['ex'])**0.5
        self.tw['envy'] = (self.tw['bety'] * self.summary['ey'])**0.5
        # Create aliases for x,y that have non-empty common prefix. The goal
        # is to make the config file entries less awkward that hold this
        # prefix:
        self.tw['posx'] = self.tw['x']
        self.tw['posy'] = self.tw['y']
        self.hook.update()
