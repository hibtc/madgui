"""
tao backend for MadQt.
"""

# TODO: determine ex/ey when opening plain bmad lattice
# - update model <-> update values
# - fix beam/twiss handling: remove redundant accessor methods
# - store + save separately: only overrides / all

# NOTE: Tao has some inconsistencies regarding data labeling. This module does
# not attempt to mitigate these, but rather mostly uses the names from one or
# the other category directly without knowing how to translate between them:
#
# - for inspecting monitor values (interaction with the control system),
#   we use `python lat_ele1 ELEM|model twiss/orbit`,         e.g. 'beta_a'
# - for showing plots, we use the builtin tao curve names,   e.g. 'beta.g.a'
# - for matching, we use the name of the tao datatype,       e.g. 'beta.a'
#
# This one seems fairly easy to mitigate, but there are harder cases, e.g.:
# - lat_ele1     -> phi_a      px        z        ??                …
# - tao datatype -> phase.a    orbit.px  orbit.z  b_curl.x          …
# - curve name   -> phase.g.a  ??        z.g.c    b_div_curl.g.cx   …
# And some of the parameters do not even have counter parts in some of the
# categories (i.e. no bmad parameter, no tao datatype, or no predefined curve)

import os
import logging
from collections import namedtuple, OrderedDict
from functools import partial

from pytao.tao import Tao

from madqt.core.unit import UnitConverter, from_config, strip_unit
from madqt.util.defaultdict import DefaultDict
from madqt.util.datastore import DataStore, SuperStore
from madqt.util.misc import (attribute_alias, sort_to_top, LazyList,
                             merged, translate_default)
from madqt.util.enum import make_enum
from madqt.resource.file import FileResource

from madqt.engine.common import (
    FloorCoords, EngineBase, SegmentBase,
    PlotInfo, CurveInfo, ElementList, ElementBase,
)


# stuff for online control:
import madqt.online.api as api


PlotData = namedtuple('PlotData', ['plot_info', 'graph_info', 'curves'])
CurveData = namedtuple('CurveData', ['name', 'info', 'data'])


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

    def __init__(self, filename, app_config, command_log):
        self.log = logging.getLogger(__name__)
        self.data = {}
        self.segment = None
        self.repo = None
        self.universe = 1
        self.command_log = command_log
        super().__init__(filename, app_config)

    def load(self, filename):
        """Load model or plain tao file."""
        path, name = os.path.split(filename)
        base, ext = os.path.splitext(name)
        self.repo = FileResource(path)
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

        self.load_init_file(data['tao']['init'], data=data)
        for filename in data['tao'].get('read', []):
            self.read(filename)
        self._load_params(data, 'beam')
        self._load_params(data, 'twiss')

    def load_init_file(self, filename, **kw):
        self.init('-init', filename, **kw)

    def load_lattice_file(self, filename, **kw):
        self.init('-lat', filename, '-noinit', **kw)

    def init(self, fileflag, filename, *args, **kw):
        self.data = kw.pop('data', {})

        with self.repo.filename(filename) as init_file:
            self.tao = Tao(
                fileflag, init_file, '-noplot',
                *args, command_log=self.command_log,
                **self.minrpc_flags())

        units = DefaultDict(self._query_unit)
        units.update(self.config['units'])
        self.utool = UnitConverter.from_config_dict(units)

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

    def _query_unit(self, name):
        return self.tao.python('lat_param_units', name)[0][0] or None

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

        super().__init__()

        self.workspace = workspace
        self.continuous_matching = True

        lat_general = self.tao.python('lat_general', workspace.universe)

        self.sequence = sequence or lat_general[0][1]
        self.range = ('#s', '#e')
        self.branch = 0

        make_element = partial(Element, self.workspace.tao, self.utool)
        self.el_names = self.tao.get_list('lat_ele_list', self.unibra)
        self.elements = ElementList(self.el_names, make_element)
        self.positions = LazyList(len(self.el_names), self._get_element_pos)

    def _get_element_pos(self, index):
        return self.utool.strip_unit('at', self.elements[index].AT)

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

    def get_twiss(self, elem, name, pos):
        """Return beam envelope at element."""
        # TODO: tao's `python lat_param_units` does currently not provide
        # units for data types, so there is no reliable way to provide units.
        # Therefore, I choose to suppress units for all data types for now:
        if name == 'envx':
            return (self.get_twiss(elem, 'beta.a', pos)
                    * self.utool.strip_unit('a_emit', self.ex()))**0.5
        if name == 'envy':
            return (self.get_twiss(elem, 'beta.b', pos)
                    * self.utool.strip_unit('b_emit', self.ey()))**0.5

        el = self.elements[elem]
        s_offset = self.utool.strip_unit('at', pos - el.AT)
        L        = self.utool.strip_unit('at', el.L)
        if s_offset < 0: s_offset = 0
        if s_offset > L: s_offset = L

        tao = self.tao
        data_d2 = '1@madqt_data_temp'
        data_d1 = '1@madqt_data_temp.1[1]'
        tao.python('data_create', data_d2, 1, 1, 1)
        try:
            tao.set('data', **{
                data_d1+'|data_source'  : 'lat',
                data_d1+'|data_type'    : name,
                data_d1+'|ele_name'     : el.NAME,
                data_d1+'|eval_point'   : 'beginning',
                data_d1+'|s_offset'     : s_offset,
            })
            data1 = tao.properties('data1', data_d1)
        finally:
            tao.python('data_destroy', data_d2)

        if not data1['good_model']:
            raise ValueError(
                "Invalid datum: {!r}! Existing datatype?".format(name))

        return data1['model_value']

    def get_twiss_at(self, elem):
        """Return beam envelope at element."""
        self.twiss.update()
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

            def get_curve_data(curve_name):
                curve_path = graph_path + '.' + curve_name
                curve_info = tao.properties('plot_curve', curve_path)
                curve_data = tao.curve_data(curve_path)
                curve_alias = graph_alias + '.' + curve_name
                return CurveData(curve_alias, curve_info, curve_data)

            return PlotData(plot_info, graph_info, list(map(
                get_curve_data, graph_info.get('curve', [])
            )))
        finally:
            tao.command('set plot', region, 'visible = F')
            tao.command('place', region, 'none')

    def get_transfer_maps(self, elems):
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
        self.twiss.update()
        plot_data = self.plot_data(name, xlim)
        info = PlotInfo(
            name=plot_data.plot_info['name']+'.'+plot_data.graph_info['name'],
            title=plot_data.graph_info['title'],
            curves=[
                CurveInfo(
                    name=curve.name,
                    short=curve.info['data_type'],
                    label=tao_legend_to_latex(curve.info['legend_text']),
                    style=self.curve_style[curve_index],
                    unit=from_config(curve.info['units'] or 1))
                for curve_index, curve in enumerate(plot_data.curves)
            ])
        data = {curve.name: curve.data for curve in plot_data.curves}
        return info, data

    def get_native_graphs(self):
        """Get a dict of graphs."""
        return {name: info['graph']['title']
                for name, info in self.tao.valid_graphs()
                if info['plot']['x_axis_type'] == 's'}

    def _retrack(self):
        self.tao.update()

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
        # TODO: create contextlib.ExitStack() for cleanup:
        tao.python('var_create', vars_v1, 1, len(variables))
        tao.python('data_create', data_d2, 1, 1, len(constraints))

        for i, expr in enumerate(variables):
            elem, attr = expr.split('->')
            index = self.get_element_index(elem)
            what = '{}[{}]|ele_name'.format(vars_v1, i+1)
            value = '{}>>{}[{}]'.format(self.unibra, index, attr)
            tao.set('var', **{what: value})

        for i, c in enumerate(constraints):
            # TODO: tao's `python lat_param_units` does currently not provide
            # units for data types, so there is no reliable way to strip safely:
            dtype = c.axis
            value = strip_unit(c.value)
            if dtype == 'sig11':
                dtype = 'beta.a'
                value = value / self.utool.strip_unit('a_emit', self.ex())
            elif dtype == 'sig33':
                dtype = 'beta.b'
                value = value / self.utool.strip_unit('b_emit', self.ey())
            elem = c.elem['name']
            data_d1 = '{}.1[{}]'.format(data_d2, i+1)
            tao.set('data', **{data_d1+'|merit_type': 'target'})
            tao.set('data', **{data_d1+'|weight': 1})
            tao.set('data', **{data_d1+'|data_source': 'lat'})
            tao.set('data', **{data_d1+'|data_type': dtype})
            tao.set('data', **{data_d1+'|meas': value})
            tao.set('data', **{data_d1+'|ele_name': elem})
            if c.pos != self.el_pos(c.elem):
                pos = self.utool.strip_unit("s", c.pos - c.elem['at'])
                tao.set('data', **{data_d1+'|eval_point': 'beginning'})
                tao.set('data', **{data_d1+'|s_offset': pos})

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
        self.elements.invalidate()
        self.twiss.invalidate()

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
            self.segment.twiss.invalidate()

    def mutable(self, key):
        return self.params[key.lower()].vary

    def default(self, key):
        return self.params[key.lower()].value    # I know…


class Element(ElementBase):

    """
    Beam line element. Lazy loads properties when needed.

    Element properties can be accessed as attributes starting with capital
    letter or as items, e.g.:

        el["name"]      el.Name
        el["knl"]       el.Knl
    """

    # TODO: use collections.ChainMap for self._merged (py3!)

    def invalidate(self, level=ElementBase.INVALIDATE_ALL):
        if level >= self.INVALIDATE_PARAM: self._params = None
        if level >= self.INVALIDATE_PARAM: self._multip = None
        if level >= self.INVALIDATE_ALL:   self._general = None
        self._merged = {'el_id': self._idx, 'name': self._name}
        self._merged.update(self._general or {})
        self._merged.update(self._params or {})
        self._merged.update(self._multip or {})

    def _retrieve(self, name):
        get_element_data, idx = self._engine.get_element_data, self._idx
        if self._general is None and name not in self._merged:
            self._general = get_element_data(idx, who='general')
            self._general['name']  = self._general['name'].lower()
            self._general['type_'] = self._general.pop('type')
            self._general['type']  = self._general.pop('key')
            self._merged.update(self._general)
        if self._params is None and name not in self._merged:
            self._params = get_element_data(idx, who='parameters')
            self._params.setdefault('l', 0)
            self._params['at'] = self._general['s'] - self._params['l']
            self._merged.update(self._params)
        if self._multip is None and name not in self._merged \
                and self._general['type'].lower() == 'multipole':
            self._multip = get_element_data(idx, who='multipole')
            self._merged.update(self._multip)


class ElementDataStore(TaoDataStore):

    def get(self):
        data = super().get()
        # TODO: rename keys, like in Element
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
        self.segment.twiss.update()
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
