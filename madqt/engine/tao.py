# encoding: utf-8
"""
tao backend for MadQt.
"""

# TODO: determine ex/ey when opening plain bmad lattice

from __future__ import absolute_import
from __future__ import unicode_literals

from six import string_types as basestring

from pytao.tao import Tao

from madqt.util.misc import (attribute_alias,
                             rename_key, merged, translate_default)

from madqt.engine.common import (
    FloorCoords, ElementInfo, EngineBase, SegmentBase
)


class Universe(EngineBase):

    """
    Contains the whole global state of a MAD-X instance and (possibly) loaded
    metadata.

    :ivar Tao tao: tao handle
    :ivar dict data: loaded model data
    :ivar Segment segment: active segment
    :ivar madqt.resource.ResourceProvider repo: resource provider
    :ivar utool: Unit conversion tool for MAD-X.
    """

    backend_libname = 'pytao'
    backend_title = 'Bmad/Tao'
    backend = attribute_alias('tao')

    def __init__(self, filename):
        self.data = {}
        self.segment = None
        self.repo = None
        self.index = 1
        super(Universe, self).__init__(filename)

    def load_dispatch(self, name, ext):
        """Load model or plain MAD-X file."""
        if ext in ('.yml', '.yaml'):
            self.load_model(name)
        elif ext == '.init':
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
        for filename in data['tao'].get('read', []):
            self.read(filename)

    def load_init_file(self, filename, **kw):
        self.init('-init', filename, **kw)

    def load_lattice_file(self, filename, **kw):
        self.init('-lat', filename, '-noinit', **kw)

    def init(self, fileflag, filename, *args, **kw):
        self.data = kw.pop('data', {})

        with self.repo.filename(filename) as init_file:
            self.tao = Tao(
                fileflag, init_file,
                '-noplot', '-gui_mode',
                *args, **self.minrpc_flags())

        # TODO: disable automatic curve + lattice recalculation:
        #   - s%global%plot_on=False
        #   - s%com%shell_interactive=True
        #   - s%global%lattice_calc_on=False
        self.tao.command('place * none')
        # init segment
        self.segment = Segment(self, self.data.get('sequence'))
        twiss_args = self.data.get('twiss')
        if twiss_args:
            self.segment.set_twiss_args_raw(twiss_args)

    def read(self, name):
        with self.repo.filename(name) as f:
            self.tao.read(f)


class Segment(SegmentBase):

    """
    Simulate one fixed segment, i.e. sequence + range.

    :ivar Tao tao:
    :ivar list elements:
    :ivar dict twiss_args:
    """

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

        self._el_indices = {el['name'].lower(): el['ix_ele']
                            for el in self.elements}

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

    def survey(self):
        return [FloorCoords(*self.tao.get_element_floor(index).flat)
                for index in range(len(self.elements))]

    def survey_elements(self):
        return self.raw_elements

    @property
    def tao(self):
        return self.universe.tao

    def parse_range(self, range):
        """Convert a range str/tuple to a tuple of :class:`ElementInfo`."""
        raise NotImplementedError

    def get_twiss(self, elem, name):
        """Return beam envelope at element."""
        raise NotImplementedError

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

    def get_transfer_map(self, beg_elem, end_elem):
        raise NotImplementedError

    def get_element_index(self, elem_name):
        """Get element index by it name."""
        return self._el_indices[elem_name.lower()]

    def get_beam_raw(self):
        beam = self.tao.properties('beam_init', self.unibra)
        # FIXME: evaluate several possible sources for emittance/beam:
        # - beam%beam_init%a_emit   (beam_init_struct -> a_emit, b_emit)
        # - lat%beam_start          (coord_struct -> x, y, px, py, ...)
        # - lat%a%emit              (mode_info_struct -> emit, sigma, ...)

        # - beam_start[emittance_a]
        translate_default(beam, 'a_emit', 0., 1.)
        translate_default(beam, 'b_emit', 0., 1.)
        return beam

    def set_beam_raw(self, beam):
        self.tao.set('beam_init', **beam)
        # Bmad has also the (unused?) `beam_start` parameter group:
        #self.tao.change('beam_start', **beam)

    _beam_params = {'x', 'px', 'y', 'py', 'z', 'pz', 't'}
    _twiss_params = {'beta_a', 'beta_b', 'alpha_a', 'alpha_b',
                     'eta_a', 'eta_b', 'etap_a', 'etap_b'}
    _twiss_args = _beam_params | _twiss_params

    def get_twiss_args_raw(self, index=0):
        data = merged(self.tao.get_element_data(index, who='orbit'),
                      self.tao.get_element_data(index, who='twiss'))
        return {k: v for k, v in data.items() if k in self._twiss_args}

    def set_twiss_args_raw(self, twiss):
        beam_start = {param: twiss[param]
                      for param in self._beam_params
                      if param in twiss}
        twiss_start = {param: twiss[param]
                       for param in self._twiss_params
                       if param in twiss}
        self.tao.change('beam_start', **beam_start)
        self.tao.change('element', 'beginning', **twiss_start)

    @property
    def unibra(self):
        """Tao string for univers@branch."""
        return '{}@{}'.format(self.universe.index, self.branch)

    def ex(self):
        # FIXME: consider Bmad's beam_start as fallback
        return self.beam['a_emit']

    def ey(self):
        return self.beam['b_emit']

    # curves

    def get_graph_data_raw(self, name):
        def rename(curve_name):
            """Normalize internal names 'beta.g.b' -> 'x'."""
            if curve_name in (name + '.g.a', name + '.g.x'):
                return 'x'
            if curve_name in (name + '.g.b', name + '.g.y'):
                return 'y'
            return curve_name
        curves = self.plot_data(name)
        values = {rename(name): values[:,1] for name, values in curves.items()}
        values['s'] = next(iter(curves.values()))[:,0]
        return values

    def get_graph_names(self):
        """Get a list of curve names."""
        return self.tao.plots() + ['alfa', 'beta', 'envelope', 'position']

    def retrack(self):
        self.tao.update()
        self.updated.emit()
