# encoding: utf-8
"""
tao backend for MadQt.
"""

# TODO: determine ex/ey when opening plain bmad lattice
# - update model <-> update values
# - fix beam/twiss handling: remove redundant accessor methods
# - store + save separately: only overrides / all
# - use units provided by tao

from __future__ import absolute_import
from __future__ import unicode_literals

import os
from collections import namedtuple, OrderedDict

from pytao.tao import Tao

import madqt.core.unit as unit
from madqt.util.datastore import DataStore, SuperStore
from madqt.util.misc import (attribute_alias, sort_to_top, logfile_name,
                             rename_key, merged, translate_default)
from madqt.util.enum import make_enum
from madqt.resource.file import FileResource

from madqt.engine.common import (
    FloorCoords, EngineBase, SegmentBase,
    PlotInfo, CurveInfo, ElementList,
)


# stuff for online control:
import madqt.online.api as api


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


class Workspace(EngineBase):

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
        self.universe = 1
        super(Workspace, self).__init__(filename, app_config)

    def load(self, filename):
        """Load model or plain tao file."""
        path, name = os.path.split(filename)
        base, ext = os.path.splitext(name)
        self.repo = FileResource(path)
        self.command_log = logfile_name(path, base, '.commands.tao')
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
                *args, command_log=self.command_log,
                **self.minrpc_flags())

        self.enums = {}     # cache: name -> class
        self.tao._create_enum_value = self._create_enum_value

        self.tao.command('place * none')
        # init segment
        self.segment = Segment(self, self.data.get('sequence'))
        twiss_args = self.data.get('twiss')
        if twiss_args:
            self.segment.set_twiss_args_raw(twiss_args)

    def read(self, name):
        with self.repo.filename(name) as f:
            self.tao.read(f)

    def _create_enum_value(self, name, value):
        if name not in self.enums:
            values = self.tao.get_list('enum', name)
            self.enums[name] = make_enum(name, values)
        return self.enums[name](value)


class Segment(SegmentBase):

    """
    Simulate one fixed segment, i.e. sequence + range.

    :ivar Tao tao:
    :ivar list elements:
    :ivar dict twiss_args:
    """

    def __init__(self, workspace, sequence):
        """
        :param Workspace workspace:
        :param str sequence:
        """

        super(Segment, self).__init__()

        self.workspace = workspace

        lat_general = self.tao.python('lat_general', workspace.universe)

        self.sequence = sequence or lat_general[0][1]
        self.range = ('#s', '#e')
        self.branch = 0

        num_elements = {
            seq.lower(): int(n_track)
            for i, seq, n_track, n_max in lat_general
        }

        el_names = self.tao.get_list('lat_ele_list', self.unibra)
        self.elements = ElementList(el_names, self.get_element_data)
        self.positions = [
            self.utool.strip_unit('s', el['at']) for el in self.elements
        ]

    def get_element_data_raw(self, index, which=None):
        data = merged(self.tao.get_element_data(index, who='general'),
                      self.tao.get_element_data(index, who='parameters'),
                      self.tao.get_element_data(index, who='multipole'))
        data['el_id'] = data['ix_ele']
        data['name'] = data['name'].lower()
        data['at'] = data['s'] - data.setdefault('l', 0)
        # for compatibility with MAD-X:
        rename_key(data, 'type', 'type_')
        rename_key(data, 'key', 'type')
        return data

    def survey(self):
        return [FloorCoords(*self.tao.get_element_floor(index).flat)
                for index in range(len(self.elements))]

    @property
    def tao(self):
        return self.workspace.tao

    @property
    def config(self):
        return self.workspace.config

    def parse_range(self, range):
        """Convert a range str/tuple to a tuple of :class:`ElementInfo`."""
        raise NotImplementedError

    def get_twiss(self, elem, name):
        """Return beam envelope at element."""
        replace = {
            'betx': 'beta_a',
            'bety': 'beta_b',
            'x': 'x',
            'y': 'y',
        }
        twiss = self.get_twiss_at(elem)
        if name == 'envx':
            return (twiss['beta_a'] * self.ex())**0.5
        elif name == 'envy':
            return (twiss['beta_b'] * self.ey())**0.5
        name = replace.get(name, name)
        return twiss[name]

    def get_twiss_at(self, elem):
        """Return beam envelope at element."""
        index = self.get_element_index(elem)
        data = merged(self.tao.get_element_data(index, who='orbit'),
                      self.tao.get_element_data(index, who='twiss'))
        return self.utool.dict_add_unit(data)

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
                raise ValueError("Invalid plot: {}".format(plot_name))
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

    def get_init_ds(self):
        return self._get_ds('init', TaoDataStore)

    def get_elem_ds(self, elem_index):
        return self._get_ds('element', ElementDataStore, element=elem_index)

    def _get_ds(self, name, DS, **kw):
        return SuperStore(OrderedDict([
            (name, DS(self, name, item, **kw))
            for name, item in self._param_set(name).items()
        ]), utool=self.utool)

    def _param_set(self, name):
        return self.config['parameter_sets'][name]

    def _get_params(self, name):
        kwargs = {'universe': self.workspace.universe, 'branch': self.branch}
        group = self._param_set('init')[name]
        return self.tao.properties(group['query'].format(**kwargs))

    # TODO: remove. this is not functional anyways
    def _set_params(self, name, data, *extra):
        pass

    # TODO: replace beam/twiss accessor functions with datastore mechanism.
    # They are not fully functional anyway (no updates!).
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

    # TODO: …
    def set_element(self, element, data):
        return self._set_params('element', data, element)

    @property
    def unibra(self):
        """Tao string for univers@branch."""
        return '{}@{}'.format(self.workspace.universe, self.branch)

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
            what = '{}[{}]|ele_name'.format(vars_v1, i+1)
            value = '{}>>{}[{}]'.format(self.unibra, index, attr)
            tao.set('var', **{what: value})

        for i, c in enumerate(constraints):
            dtype = DATA_TYPES[c.axis]
            value = self.utool.strip_unit(c.axis, c.value)
            elem = c.elem['name']
            data_d1 = '{}.1[{}]'.format(data_d2, i+1)
            tao.set('data', **{data_d1+'|merit_type': 'target'})
            tao.set('data', **{data_d1+'|weight': 1})
            tao.set('data', **{data_d1+'|data_source': 'lat'})
            tao.set('data', **{data_d1+'|data_type': dtype})
            tao.set('data', **{data_d1+'|meas': value})
            tao.set('data', **{data_d1+'|ele_name': elem})

        tao.command('use', 'var', vars_v1)
        tao.command('use', 'dat', data_d2)

        # re-enable recalculation
        tao.set('global', optimizer='lmdif')
        tao.set('global', lattice_calc_on='T')

        tao.command('run_optimizer')
        tao.command('run_optimizer')

        # TODO: extract variables?

        # cleanup behind us, leave recalculation disabled by default
        tao.set('global', lattice_calc_on='F')
        tao.python('var_destroy', vars_v1)
        tao.python('data_destroy', data_d2)

        # TODO: update only modified elements
        self.elements.update()
        self.retrack()

    def get_magnet(self, elem, conv):
        return MagnetBackend(self, elem, conv.backend_keys)

    def get_monitor(self, elem):
        return MonitorBackend(self, elem)

    def get_knob(self, expr):
        if '->' not in expr:
            raise NotImplementedError(
                "Can't evaluate arbitrary expression: {!r}".format(expr))
        name, attr = expr.split('->')
        return self.elements[name][attr]

    def set_knob(self, knob, value):
        if not isinstance(knob, tuple):
            raise TypeError("Unsupported knob datatype: {!r}".format(knob))
        elem, attr = knob
        elid = self.elements[elem]['el_id']
        self.get_elem_ds(elid).substores['parameters'].update({attr: value})


# TODO: dumb this down…
class TaoDataStore(DataStore):

    def __init__(self, segment, name, conf, **kw):
        self.segment = segment
        self.conf = conf
        self.label = name.title()
        self.data_key = name
        self.kw = kw

    def _update_params(self):
        kwargs = dict(self.kw, universe=self.segment.workspace.universe,
                      branch=self.segment.branch)
        query = self.segment.tao.parameters
        self.params = OrderedDict(
            (param.name.lower(), param)
            for param in query(self.conf['query'].format(**kwargs)).values()
        )

    def get(self):
        self._update_params()
        return self.segment.utool.dict_add_unit(OrderedDict(
            (param.name.title(), param.value)
            for param in self.params.values()))

    def update(self, values):
        self._update_params()
        has_changed = False
        for key, val in values.items():
            key = key.lower()
            par = self.params.get(key)
            val = self.segment.utool.strip_unit(key, val)
            if par is None or val is None or not par.vary or par.value == val:
                continue
            command = self.conf['write'].format(key=key, val=val, **self.kw)
            self.segment.tao.command(command)
            has_changed = True
        if has_changed:
            self.segment.retrack()

    def mutable(self, key):
        return self.params[key.lower()].vary

    def default(self, key):
        return self.params[key.lower()].value    # I know…


class ElementDataStore(TaoDataStore):

    def get(self):
        data = super(ElementDataStore, self).get()
        # TODO: rename keys, like in tao.get_element_data_raw
        return sort_to_top(data, [
            'Name',
            'Key',
            'S',
            'L',
        ])


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


#----------------------------------------
# stuff for online control
#----------------------------------------

class MagnetBackend(api.ElementBackend):

    """Mitigates r/w access to the properties of an element."""

    def __init__(self, segment, elem, keys):
        self._segment = segment
        self._elem = elem
        self._keys = keys

    def get(self):
        """Get dict of values from MAD-X."""
        data = self._segment.elements[self._elem]
        return {key: data[key] for key in self._keys}

    def set(self, values):
        """Store values to MAD-X."""
        # TODO: update cache
        seg = self._segment
        index = seg.get_element_index(self._elem)
        elem = '{}>>{}'.format(seg.unibra, index)
        values = self._segment.utool.dict_strip_unit(values)
        self._segment.tao.set('element', elem, **values)


class MonitorBackend(api.ElementBackend):

    """Mitigates read access to a monitor."""

    # TODO: handle split h-/v-monitor

    def __init__(self, segment, element):
        self._segment = segment
        self._element = element

    def get(self, values):
        tao = self._segment.tao
        index = self._segment.get_element_index(self._element)
        orbit = tao.get_element_data(index, who='orbit')
        twiss = tao.get_element_data(index, who='twiss')
        return self._segment.utool.dict_add_unit({
            'betx': twiss['beta_a'],
            'bety': twiss['beta_b'],
            'x': orbit['x'],
            'y': orbit['y'],
        })

    def set(self, values):
        raise NotImplementedError("Can't set TWISS: monitors are read-only!")
