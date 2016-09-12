# encoding: utf-8
"""
tao backend for MadQt.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from collections import namedtuple
import os
import subprocess

from six import string_types as basestring
import numpy as np
import yaml

from pytao.tao import Tao

from madqt.core.base import Object, Signal

from madqt.core.unit import UnitConverter
from madqt.resource.file import FileResource
from madqt.resource.package import PackageResource


ElementInfo = namedtuple('ElementInfo', ['name', 'index', 'at'])


class Universe(Object):

    """
    Contains the whole global state of a MAD-X instance and (possibly) loaded
    metadata.

    :ivar Tao tao: tao handle
    :ivar dict data: loaded model data
    :ivar Segment segment: active segment
    :ivar madqt.resource.ResourceProvider repo: resource provider
    :ivar utool: Unit conversion tool for MAD-X.
    """

    destroyed = Signal()

    def __init__(self, filename):
        super(Universe, self).__init__()
        self.data = {}
        self.segment = None
        self.repo = None
        self.init_files = []

        self.config = PackageResource('madqt.engine').yaml('madx.yml')
        self.utool = UnitConverter.from_config_dict(self.config['units'])
        self.load(filename)

    def destroy(self):
        """Annihilate current universe. Stop MAD-X interpreter."""
        if self.rpc_client:
            self.rpc_client.close()
        self.tao = None
        if self.segment is not None:
            self.segment.destroy()
        self.destroyed.emit()

    def call(self, name):
        with self.repo.filename(name) as f:
            self.tao.read(f)
        self.init_files.append(name)

    @property
    def rpc_client(self):
        """Low level MAD-X RPC client."""
        return self.tao and self.tao._service

    @property
    def remote_process(self):
        """MAD-X process."""
        return self.tao and self.tao._process

    def load(self, filename):
        """Load model or plain MAD-X file."""
        path, name = os.path.split(filename)
        self.repo = FileResource(path)
        ext = os.path.splitext(name)[1]
        if ext.lower() in ('.yml', '.yaml'):
            self.load_model(name)
        elif ext.lower() == '.init':
            self.load_init_file(name)
        else:
            self.load_lattice_files([name])

    def load_model(self, filename):
        """Load model data from file."""
        data = self.repo.yaml(filename, encoding='utf-8')
        #self.check_compatibility(data)
        self.data = data

        # stdin=None leads to an error on windows when STDIN is broken.
        # therefore, we need set stdin=os.devnull by passing stdin=False:
        with self.repo.filename(data['tao']['init']) as init_file:
            self.tao = Tao(
                '-init', init_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=False)
        self.load_lattice_files(data['tao'].get('read', []))

        self._load_params(data, 'beam')
        self._load_params(data, 'twiss')
        segment_data = {'sequence', 'range', 'beam', 'twiss'}
        if all(data.get(p) for p in segment_data):
            self.init_segment(data)

    def load_init_file(self, filename):
        raise NotImplementedError

    def load_lattice_files(self, filenames):
        """Load a plain Bmad lattice file."""
        for filename in filenames:
            self.call(filename)

    def _load_params(self, data, name):
        """Load parameter dict from file if necessary and add units."""
        vals = self.data.get(name, {})
        if isinstance(vals, basestring):
            vals = self.repo.yaml(vals, encoding='utf-8')
        data[name] = self.utool.dict_add_unit(vals)

    def init_segment(self, data):
        """Create a segment."""
        self.segment = Segment(
            universe=self,
            sequence=data['sequence'],
            range=data['range'],
            beam=data['beam'],
            twiss_args=data['twiss'],
        )



class Segment(Object):

    """
    Simulate one fixed segment, i.e. sequence + range.

    :ivar Tao tao:
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

    updated = Signal()
    destroyed = Signal()
    showIndicators = Signal()
    hideIndicators = Signal()
    show_element_indicators = False

    def __init__(self, universe, sequence, range, beam, twiss_args):
        """
        :param Universe universe:
        :param str sequence:
        :param tuple range:
        """

        super(Segment, self).__init__()

        self.universe = universe
        self.sequence = sequence
        self.range = range
        self.beam = beam
        self.twiss_args = twiss_args
        self.elements = []

        self.twiss()

    @property
    def tao(self):
        return self.universe.tao

    @property
    def utool(self):
        return self.universe.utool

    @property
    def data(self):
        return {
            'sequence': self.sequence,
            'range': self.range,
            'beam': self.beam,
            'twiss': self.twiss_args,
        }

    def get_element_info(self, element):
        """Get :class:`ElementInfo` from element name or index."""
        raise NotImplementedError

    def parse_range(self, range):
        """Convert a range str/tuple to a tuple of :class:`ElementInfo`."""
        raise NotImplementedError

    def destroy(self):
        self.universe.segment = None
        self.destroyed.emit()

    def element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        return None

    def get_element_index(self, elem):
        """Get element index by it name."""
        raise NotImplementedError

    def get_twiss(self, elem, name):
        """Return beam envelope at element."""
        raise NotImplementedError

    def contains(self, element):
        raise NotImplementedError

    def twiss(self):
        """Recalculate TWISS parameters."""
        results = self.raw_twiss()
        self.raw_tw = results

        # Update TWISS results
        self.tw = self.utool.dict_add_unit(results)

        # FIXME:
        ex = self.data['beam']['ex']
        ey = self.data['beam']['ey']

        # data post processing
        self.pos = self.tw['s']
        self.tw['envx'] = (self.tw['betx'] * ex)**0.5
        self.tw['envy'] = (self.tw['bety'] * ey)**0.5


        # Create aliases for x,y that have non-empty common prefix. The goal
        # is to make the config file entries less awkward that hold this
        # prefix:
        #self.tw['posx'] = self.tw['x']
        #self.tw['posy'] = self.tw['y']
        self.updated.emit()

    def raw_twiss(self, **kwargs):
        self.tao.update()
        curves = {
            curve: self.tao.curve_data(curve)
            for plot in ('beta',)
            for curve in self.tao.curve_names(plot)
        }
        twiss = {name: values[:,1] for name, values in curves.items()}
        twiss['s'] = next(iter(curves.values()))[:,0]
        twiss['betx'] = twiss['beta.g.a']
        twiss['bety'] = twiss['beta.g.b']
        return twiss

    def get_transfer_map(self, beg_elem, end_elem):
        raise NotImplementedError
