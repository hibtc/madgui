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
FloorCoords = namedtuple('FloorCoords', ['x', 'y', 'z', 'theta', 'phi', 'psi'])


def rename_key(d, name, new):
    if name in d:
        d[new] = d.pop(name)


def merged(d1, *others):
    r = d1.copy()
    for d in others:
        r.update(d)
    return r


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

    backend_name = 'Bmad/Tao'

    destroyed = Signal()

    def __init__(self, filename):
        super(Universe, self).__init__()
        self.data = {}
        self.segment = None
        self.repo = None
        self.index = 1

        # TODO: use Bmad specific units!
        self.config = PackageResource('madqt.engine').yaml('tao.yml')
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
            self.load_lattice_file(name)

    def load_model(self, filename):
        """Load model data from file."""
        data = self.repo.yaml(filename, encoding='utf-8')
        #self.check_compatibility(data)
        self._load_params(data, 'beam')
        self._load_params(data, 'twiss')

        self.load_init_file(data['tao']['init'], data=data)
        self.read_lattice_files(data['tao'].get('read', []))

    def load_init_file(self, filename, **kw):
        self.init('-init', filename, **kw)

    def load_lattice_file(self, filename, **kw):
        self.init('-lat', filename, '-noinit', **kw)

    def init(self, fileflag, filename, *args, **kw):
        self.data = kw.pop('data', {})

        # stdin=None leads to an error on windows when STDIN is broken.
        # therefore, we need set stdin=os.devnull by passing stdin=False:
        with self.repo.filename(filename) as init_file:
            self.tao = Tao(
                fileflag, init_file,
                '-noplot', '-gui_mode',
                *args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=False)

        # TODO: disable automatic curve + lattice recalculation:
        #   - s%global%plot_on=False
        #   - s%com%shell_interactive=True
        #   - s%global%lattice_calc_on=False
        self.tao.command('place * none')
        self.init_segment()

    def read_lattice_files(self, filenames):
        """Load a plain Bmad lattice file."""
        for filename in filenames:
            self.call(filename)

    def _load_params(self, data, name):
        """Load parameter dict from file if necessary and add units."""
        vals = data.get(name, {})
        if isinstance(vals, basestring):
            vals = self.repo.yaml(vals, encoding='utf-8')
        data[name] = self.utool.dict_add_unit(vals)

    def init_segment(self):
        """Create a segment."""
        self.segment = Segment(self, self.data.get('sequence'))
        twiss_args = self.data.get('twiss')
        if twiss_args:
            self.segment.set_twiss_args(twiss_args)



class Segment(Object):

    """
    Simulate one fixed segment, i.e. sequence + range.

    :ivar Tao tao:
    :ivar list elements:
    :ivar dict twiss_args:
    """

    updated = Signal()
    destroyed = Signal()
    showIndicators = Signal()
    hideIndicators = Signal()
    _show_element_indicators = False

    def __init__(self, universe, sequence):
        """
        :param Universe universe:
        :param str sequence:
        """

        super(Segment, self).__init__()

        self.universe = universe

        lat_general = self.tao.python('lat_general', universe.index)

        self.sequence = sequence or lat_general[0][1]
        self.range = ('#s', '#e')
        self.branch = 0

        num_elements = {
            seq.lower(): int(n_track)
            for i, seq, n_track, n_max in lat_general
        }

        num_elements_seg = num_elements[self.sequence.lower()]

        self.raw_elements = [
            self.get_element_data_raw(i)
            for i in range(num_elements_seg)]
        self.elements = [
            self.utool.dict_add_unit(elem)
            for elem in self.raw_elements]

        self._el_indices = {el['name']: el['ix_ele']
                            for el in self.elements}

        self.twiss()

    def get_element_data_raw(self, index):
        data = merged(self.tao.get_element_data(index, who='general'),
                      self.tao.get_element_data(index, who='parameters'),
                      self.tao.get_element_data(index, who='multipole'))
        data['name'] = data['name'].lower()
        data['at'] = data['s'] - data['l']
        # for compatibility with MAD-X:
        rename_key(data, 'type', 'type_')
        rename_key(data, 'key', 'type')
        return data

    def get_element_data(self, index):
        return self.utool.dict_add_unit(self.get_element_data_raw(index))

    def survey(self):
        return [FloorCoords(*self.tao.get_element_floor(index).flat)
                for index in range(len(self.elements))]

    def survey_elements(self):
        return self.raw_elements

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
        if isinstance(element, ElementInfo):
            return element
        if isinstance(element, basestring):
            element =  self._el_indices[element]
        if element < 0:
            element += len(self.elements)
        element_data = self.get_element_data(element)
        return ElementInfo(element_data['name'], element, element_data['at'])

    def parse_range(self, range):
        """Convert a range str/tuple to a tuple of :class:`ElementInfo`."""
        raise NotImplementedError

    def destroy(self):
        self.universe.segment = None
        self.destroyed.emit()

    def element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        return None

    def element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        if pos is None:
            return None
        for elem in self.elements:
            at, L = elem['at'], elem['l']
            if pos >= at and pos <= at+L:
                return elem
        return None

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

        # FIXME: consider Bmad's beam_start as fallback
        ex = self.beam['a_emit']
        ey = self.beam['b_emit']

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

    def plot_data(self, name, region='r11'):
        tao = self.tao
        tao.command('place', region, name)
        tao.command('set plot', region, 'visible = T')
        try:
            return {name+'.'+curve.split('.', 1)[1]: tao.curve_data(curve)
                    for curve in tao.curve_names(region)}
        finally:
            tao.command('set plot', region, 'visible = F')
            tao.command('place', region, 'none')

    def raw_twiss(self, **kwargs):
        self.tao.update()
        curves = {
            curve: curve_data
            for plot in ('beta',)
            for curve, curve_data in self.plot_data(plot).items()
        }
        twiss = {name: values[:,1] for name, values in curves.items()}
        twiss['s'] = next(iter(curves.values()))[:,0]
        twiss['betx'] = twiss['beta.g.a']
        twiss['bety'] = twiss['beta.g.b']
        return twiss

    def get_transfer_map(self, beg_elem, end_elem):
        raise NotImplementedError


    @property
    def show_element_indicators(self):
        return self._show_element_indicators

    @show_element_indicators.setter
    def show_element_indicators(self, show):
        if show == self._show_element_indicators:
            return
        self._show_element_indicators = show
        if show:
            self.showIndicators.emit()
        else:
            self.hideIndicators.emit()

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

    def get_beam(self):
        beam = self.tao.properties('beam_init', self.unibra)
        # FIXME: evaluate several possible sources for emittance/beam:
        # - beam%beam_init%a_emit   (beam_init_struct -> a_emit, b_emit)
        # - lat%beam_start          (coord_struct -> x, y, px, py, ...)
        # - lat%a%emit              (mode_info_struct -> emit, sigma, ...)

        # - beam_start[emittance_a]
        _translate_default(beam, 'a_emit', 0., 1.)
        _translate_default(beam, 'b_emit', 0., 1.)
        return self.utool.dict_add_unit(beam)

    def set_beam(self, beam):
        self.tao.set('beam_init', **beam)
        # Bmad has also the (unused?) `beam_start` parameter group:
        #self.tao.change('beam_start', **beam)

    beam = property(get_beam, set_beam)

    _beam_params = {'x', 'px', 'y', 'py', 'z', 'pz', 't'}
    _twiss_params = {'beta_a', 'beta_b', 'alpha_a', 'alpha_b',
                     'eta_a', 'eta_b', 'etap_a', 'etap_b'}
    _twiss_args = _beam_params | _twiss_params

    def get_twiss_args(self, index=0):
        data = merged(self.tao.get_element_data(index, who='orbit'),
                      self.tao.get_element_data(index, who='twiss'))
        return {k: v for k, v in data.items() if k in self._twiss_args}

    def set_twiss_args(self, twiss):
        beam_start = {param: twiss[param]
                      for param in self._beam_params
                      if param in twiss}
        twiss_start = {param: twiss[param]
                       for param in self._twiss_params
                       if param in twiss}
        self.tao.change('beam_start', **beam_start)
        self.tao.change('element', 'beginning', **twiss_start)

    twiss_args = property(get_twiss_args, set_twiss_args)


    @property
    def unibra(self):
        """Tao string for univers@branch."""
        return '{}@{}'.format(self.universe.index, self.branch)


def _translate_default(d, name, old_default, new_default):
    if d[name] == old_default:
        d[name] = new_default
