# encoding: utf-8
"""
Session component for the MadGUI application.
"""

# force new style imports
from __future__ import absolute_import

# standard library
from collections import namedtuple
import subprocess

# 3rd party
from cpymad.madx import Madx
from cpymad.util import normalize_range_name

import numpy as np

# internal
from madgui.core.plugin import HookCollection
from madgui.util.common import temp_filename

# exported symbols
__all__ = [
    'ElementInfo',
    'Session',
    'Segment',
]


class Session(object):

    """
    Contains the whole global state of a MAD-X instance and (possibly) loaded
    metadata.

    :ivar utool: Unit conversion tool
    :ivar libmadx: Low level cpymad API
    :ivar madx: CPyMAD interpretor instance
    :ivar model: CPyMAD model
    :ivar segment: Currently active segment

    :ivar rpc_client: Low level MAD-X RPC client
    :ivar remote_process: MAD-X process
    """

    # TODO: more logging
    # TODO: automatically switch directories when CALLing files?
    # TODO: saveable state

    def __init__(self, utool):
        """Initialize with (Madx, Model)."""
        self.utool = utool
        self.libmadx = None
        self.madx = None
        self.model = None
        self.repo = None
        self.segment = None
        self.rpc_client = None
        self.remote_process = None

    def start(self):
        self.stop()
        # stdin=None leads to an error on windows when STDIN is broken.
        # therefore, we need use stdin=os.devnull:
        self.madx = madx = Madx(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=False,
            bufsize=0)
        self.rpc_client = madx._service
        self.remote_process = madx._process
        self.libmadx = madx._libmadx

    def stop(self):
        if self.rpc_client:
            self.rpc_client.close()
        self.rpc_client = None
        self.remote_process = None
        self.libmadx = None
        self.madx = None
        if self.segment is not None:
            self.segment.destroy()


ElementInfo = namedtuple('ElementInfo', ['name', 'index', 'at'])


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

    def __init__(self, session, sequence, twiss_args, beam, range='#s/#e'):
        """
        :param Session session:
        :param str sequence:
        :param tuple range:
        """
        self.hook = HookCollection(
            update=None,
            remove=None,
            show_element_indicators=None,
        )

        self.session = session
        self.sequence = session.madx.sequences[sequence]
        self._twiss_args = twiss_args
        self._show_element_indicators = False

        self.start, self.stop = self.parse_range(range)
        self.range = (normalize_range_name(self.start.name),
                      normalize_range_name(self.stop.name))

        raw_elements = self.sequence.elements
        # TODO: provide uncached version of elements with units:
        self.elements = list(map(
            session.utool.dict_add_unit, raw_elements))
        self.madx = session.madx
        self.utool = session.utool

        session.segment = self

        # TODO: self.hook.create(self)

        self.beam = beam
        self.twiss()

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

    def destroy(self):
        self.session.segment = None
        self.hook.remove()

    @property
    def show_element_indicators(self):
        return self._show_element_indicators

    @show_element_indicators.setter
    def show_element_indicators(self, show):
        if show == self._show_element_indicators:
            return
        self._show_element_indicators = show
        self.hook.show_element_indicators()

    @property
    def twiss_args(self):
        return self._twiss_args

    @twiss_args.setter
    def twiss_args(self, twiss_args):
        self._twiss_args = twiss_args
        self.twiss()

    @property
    def beam(self):
        """Get the beam parameter dictionary."""
        return self.session.utool.dict_add_unit(self.sequence.beam)

    @beam.setter
    def beam(self, beam):
        """Set beam from a parameter dictionary."""
        beam = self.utool.dict_strip_unit(beam)
        beam = dict(beam, sequence=self.sequence.name)
        self.madx.command.beam(**beam)
        self.twiss()

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

    def get_twiss(self, elem, name):
        """Return beam envelope at element."""
        element = self.get_element_info(elem)
        if not self.contains(element):
            return None
        return self.tw[name][element.index - self.start.index]

    def contains(self, element):
        return (self.start.index <= element.index and
                self.stop.index >= element.index)

    def twiss(self):
        """Recalculate TWISS parameters."""
        results = self.raw_twiss()
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

    def raw_twiss(self, **kwargs):
        twiss_init = self.utool.dict_strip_unit(self.twiss_args)
        twiss_args = {
            'sequence': self.sequence.name,
            'range': self.range,
            'columns': self._columns,
            'twiss_init': twiss_init,
        }
        twiss_args.update(kwargs)
        return self.madx.twiss(**twiss_args)

    def get_transfer_map(self, beg_elem, end_elem):
        """
        Get the transfer matrix R(i,j) between the two elements.

        This requires a full twiss call, so don't do it too often.
        """
        info = self.get_element_info
        madx = self.madx
        madx.command.select(flag='sectormap', clear=True)
        madx.command.select(flag='sectormap', range=info(beg_elem).name)
        madx.command.select(flag='sectormap', range=info(end_elem).name)
        with temp_filename() as sectorfile:
            self.raw_twiss(sectormap=True, sectorfile=sectorfile)
        sectortable = madx.get_table('sectortable')
        def sectormap(i, j):
            return sectortable['r{}{}'.format(i, j)][-1]
        return np.array([[sectormap(i+1, j+1)
                          for j in range(6)]
                         for i in range(6)])
