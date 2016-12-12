# encoding: utf-8
"""
tao backend for MadQt.
"""

# TODO: determine ex/ey when opening plain bmad lattice

from __future__ import absolute_import
from __future__ import unicode_literals

from collections import namedtuple

import re

from six import string_types as basestring

from pytao.tao import Tao

import madqt.core.unit as unit
from madqt.util.misc import (attribute_alias,
                             rename_key, merged, translate_default)

from madqt.engine.common import (
    FloorCoords, ElementInfo, EngineBase, SegmentBase,
    PlotInfo, CurveInfo, ElementList,
)


PlotData = namedtuple('PlotData', ['plot_info', 'graph_info', 'curves'])
CurveData = namedtuple('CurveData', ['name', 'info', 'data'])

DATA_TYPES = {
    'betx': 'beta.a',
    'bety': 'beta.b',
    'x': 'orbit.x',
    'y': 'orbit.y',
    'posx': 'orbit.x',
    'posy': 'orbit.y',
}


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

    def __init__(self, filename, app_config):
        self.data = {}
        self.segment = None
        self.repo = None
        self.index = 1
        super(Universe, self).__init__(filename, app_config)

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

        el_names = self.tao.get_list('lat_ele_list', self.unibra)
        self.elements = ElementList(el_names, self.get_element_data)

    def get_element_data_raw(self, index):
        data = merged(self.tao.get_element_data(index, who='general'),
                      self.tao.get_element_data(index, who='parameters'),
                      self.tao.get_element_data(index, who='multipole'))
        data['el_id'] = data['ix_ele']
        data['name'] = data['name'].lower()
        data['at'] = data['s'] - data['l']
        # for compatibility with MAD-X:
        rename_key(data, 'type', 'type_')
        rename_key(data, 'key', 'type')
        return data

    def survey(self):
        return [FloorCoords(*self.tao.get_element_floor(index).flat)
                for index in range(len(self.elements))]

    @property
    def tao(self):
        return self.universe.tao

    @property
    def config(self):
        return self.universe.config

    def parse_range(self, range):
        """Convert a range str/tuple to a tuple of :class:`ElementInfo`."""
        raise NotImplementedError

    def get_twiss(self, elem, name):
        """Return beam envelope at element."""
        raise NotImplementedError

    def plot_data(self, plot_name, xlim, region='r11'):
        tao = self.tao
        tao.command('place', region, plot_name)
        tao.command('set plot', region, 'visible = T')
        try:
            tao.command('x_scale', region, *(xlim or ()))
            plot_info = tao.properties('plot1', region)
            graphs = plot_info.get('graph', [])
            if len(graphs) != 1:
                raise ValueError("Need exactly one graph, found {} graphs."
                                 .format(len(graphs)))
            graph_name, = graphs
            graph_path = region + '.' + graph_name
            graph_info = tao.properties('plot_graph', graph_path)
            if not graph_info.get('valid'):
                raise ValueError("Invalid plot.")
            graph_alias = plot_info['name'] + '.' + graph_name

            return PlotData(plot_info, graph_info, [
                CurveData(curve_alias, curve_info, curve_data)
                for curve_name in graph_info.get('curve', [])
                for curve_path in [graph_path + '.' + curve_name]
                for curve_info in [tao.properties('plot_curve', curve_path)]
                for curve_data in [tao.curve_data(curve_path)]
                for curve_alias in [graph_alias + '.' + curve_name]
            ])
        finally:
            tao.command('set plot', region, 'visible = F')
            tao.command('place', region, 'none')

    def get_transfer_map(self, beg_elem, end_elem):
        raise NotImplementedError

    def get_element_index(self, elem_name):
        """Get element index by it name."""
        return self.elements.index(elem_name)

    def get_beam_conf(self):
        return self._get_param_conf('beam')

    def get_twiss_conf(self):
        return self._get_param_conf('twiss')

    def _param_set(self, name):
        return self.config['parameter_sets'][name]

    def _get_param_conf(self, name):
        from madqt.widget.params import ParamSpec

        def prepare_group(group):
            group['readonly']  = readonly  = set(group.get('readonly', ()))
            group['readwrite'] = readwrite = set(group.get('readwrite', ()))
            group['auto']      = auto      = set(group.get('auto', ()))
            group['explicit']  = readonly | readwrite | auto
            group.setdefault('implicit', 'auto')
            return group

        def param_mode(name, group):
            if name in group['readwrite']:
                return 'readwrite'
            if name in group['readonly']:
                return 'readonly'
            if name in group['auto']:
                return 'auto'
            return group['implicit']

        def editable(mode, auto):
            return (mode == 'readwrite' or mode == True or
                    mode == 'auto' and auto)

        query = self.tao.parameters
        conf = self._param_set(name)
        spec = [
            ParamSpec(param.name, param.value, editable(mode, param.vary))
            for group in map(prepare_group, conf['params'])
            for param in query(group['query'].format(self.unibra)).values()
            for mode in [param_mode(param.name, group)]
            if mode in ('readwrite', 'readonly', 'auto', True, False)
        ]
        data = {param.name: param.value for param in spec}
        return (spec, self.utool.dict_add_unit(data), conf)

    def _get_params(self, name):
        return merged(*(self.tao.properties(group['query'].format(self.unibra))
                        for group in self._param_set(name)['params']))

    def _set_params(self, name, data):
        for group in self._param_set(name)['params']:
            for key in group.get('readwrite', []):
                val = data.get(key)
                if val is not None:
                    command = group['write'].format(key, val)
                    self.tao.command(command)

    def get_beam_raw(self):
        beam = self._get_params('beam')
        translate_default(beam, 'a_emit', 0., 1.)
        translate_default(beam, 'b_emit', 0., 1.)
        return beam

    def set_beam_raw(self, beam):
        self._set_params('beam', beam)

        # NOTE: species can be `set beam_init species = NUMBER`, where
        #  NUMBER = charge_sign * (
        #       mass_number +
        #       atomic_number * 100000 +
        #       charge_number * 100000000)
        # see: sim_utils/interfaces/particle_species_mod.f90 -> species_id()

    def get_twiss_args_raw(self, index=0):
        return self._get_params('twiss')

    def set_twiss_args_raw(self, twiss):
        return self._set_params('twiss', twiss)

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

    def get_native_graph_data(self, name, xlim):
        plot_data = self.plot_data(name, xlim)
        info = PlotInfo(
            name=plot_data.plot_info['name']+'.'+plot_data.graph_info['name'],
            short=plot_data.plot_info['name'],
            title=plot_data.graph_info['title'],
            curves=[
                CurveInfo(
                    name=curve.name,
                    short=curve_short_name(plot_data, curve.info),
                    label=tao_legend_to_latex(curve.info['legend_text']),
                    style=self.curve_style[curve_index],
                    unit=unit.from_config(curve.info['units'] or 1))
                for curve_index, curve in enumerate(plot_data.curves)
            ])
        data = {curve.name: curve.data for curve in plot_data.curves}
        return info, data

    def get_native_graphs(self):
        """Get a dict of graphs."""
        return {name.split('.')[0]: (name, info['graph']['title'])
                for name, info in self.tao.valid_graphs()
                if info['plot']['x_axis_type'] == 's'}

    def retrack(self):
        self.tao.update()
        self.updated.emit()

    def get_best_match_pos(self, pos):
        """Find optics element by longitudinal position."""
        el_pos = lambda el: el['at'] + el['l']
        elem = min(filter(self.can_match_at, self.elements),
                   key=lambda el: abs(el_pos(el)-pos))
        return (elem, el_pos(elem))

    def create_constraint(self, at, key, value):
        pass

    def match(self, variables, constraints):
        tao = self.tao

        # make sure recalculation is disabled during setup
        tao.set('global', lattice_calc_on='F')
        tao.command('veto', 'var', '*')
        tao.command('veto', 'dat', '*@*')

        # setup data/variable structures
        data_d2 = '1@madqt_data_temp'
        vars_v1 = 'madqt_vars_temp'
        tao.python('var_create', vars_v1, 1, len(variables))
        tao.python('data_create', data_d2, 1, 1, len(constraints))

        for i, expr in enumerate(variables):
            elem, attr = expr.split('->')
            index = self.get_element_index(elem)
            what = vars_v1 + '|ele_name'
            value = '{}>>{}[{}]'.format(self.unibra, index, attr)
            tao.set('var', **{what: value})

        for i, c in enumerate(constraints):
            dtype = DATA_TYPES[c.axis]
            data_d1 = '{}[{}]'.format(data_d2, i+1)
            tao.set('data', **{data_d1+'|ele_name': c.elem})
            tao.set('data', **{data_d1+'|data_type': dtype})
            tao.set('data', **{data_d1+'|meas': c.value})

        tao.command('use', 'var', vars_v1)
        tao.command('use', 'dat', data_d2)

        # re-enable recalculation
        tao.set('global', optimizer='lmdif')
        tao.set('global', lattice_calc_on='T')
        # TODO: extract variables?

        # cleanup behind us, leave recalculation disabled by default
        tao.set('global', lattice_calc_on='F')
        tao.python('var_destroy', data_d2)
        tao.python('data_destroy', data_d2)

        self.retrack()


# http://plplot.sourceforge.net/docbook-manual/plplot-html-5.11.1/characters.html#greek
ROMAN_TO_GREEK = {
    'a': 'alpha',   'b': 'beta',    'g': 'gamma',   'd': 'delta',
    'e': 'epsilon', 'z': 'zeta',    'y': 'eta',     'h': 'theta',
    'i': 'iota',    'k': 'kappa',   'l': 'lambda',  'm': 'mu',
    'n': 'nu',      'c': 'xi',      'o': 'o',       'p': 'pi',
    'r': 'rho',     's': 'sigma',   't': 'tau',     'u': 'upsilon',
    'f': 'phi',     'x': 'chi',     'q': 'psi',     'w': 'omega',
}


def tao_legend_to_latex(text):
    """Translate a pgplot (?) legend text to a matplotlib legend (LaTeX)."""
    # superscript/subscript
    while True:
        up   = text.find('\\u')
        down = text.find('\\d')
        if up == -1 or down == -1:
            break
        if up < down:
            mod = '^'
            beg = up
            end = down
        else:
            mod = '_'
            beg = down
            end = up
        text = text[:beg] + '$' + mod + '{' + text[beg+2:end] + '}$' + text[end+2:]
    # greek letters
    while True:
        pos = text.find('\\g')
        if pos == -1:
            break
        roman = text[pos+2]
        greek = ROMAN_TO_GREEK[roman]
        text = '{}$\\{}${}'.format(text[:pos], greek, text[pos+3:])
    # join adjacent math sections
    text = text.replace('$$', '')
    return text


def curve_short_name(plot_data, curve_info):
    return '{}_{}'.format(plot_data.plot_info['name'], curve_info['name'])
