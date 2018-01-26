"""
MAD-X backend for MadQt.
"""

import os
from collections import OrderedDict, defaultdict
from functools import partial
import itertools
import logging

import numpy as np

from cpymad.madx import Madx
from cpymad.util import normalize_range_name

from madqt.core.base import Cache
from madqt.resource import yaml
from madqt.core.unit import UnitConverter, from_config, isclose, number_types
from madqt.util.misc import attribute_alias, cachedproperty, sort_to_top
from madqt.resource.file import FileResource
from madqt.resource.package import PackageResource
from madqt.util.datastore import DataStore, SuperStore

from madqt.engine.common import (
    FloorCoords, ElementInfo, BaseModel,
    PlotInfo, CurveInfo, ElementList, ElementBase,
)


# stuff for online control:
import madqt.online.api as api
from cpymad.types import Expression
from cpymad.util import is_identifier
from madqt.util.symbol import SymbolicValue


__all__ = [
    'ElementInfo',
    'Model',
]


class Model(BaseModel):

    """
    Contains the whole global state of a MAD-X instance and (possibly) loaded
    metadata.

    :ivar Madx madx: CPyMAD interpreter
    :ivar dict data: loaded model data
    :ivar madqt.resource.ResourceProvider repo: resource provider
    :ivar utool: Unit conversion tool for MAD-X.
    """

    backend_libname = 'cpymad'
    backend_title = 'MAD-X'
    backend = attribute_alias('madx')

    def __init__(self, filename, app_config, command_log):
        super().__init__()
        self.twiss = Cache(self._retrack)
        self.log = logging.getLogger(__name__)
        self.data = {}
        self.repo = None
        self.init_files = []
        self.command_log = command_log
        self.app_config = app_config
        self.config = PackageResource('madqt.engine').yaml('madx.yml')
        self.load(filename)
        self.twiss.invalidate()

    @property
    def libmadx(self):
        """Access to the low level cpymad API."""
        return self.madx and self.madx._libmadx

    def call(self, name):
        """Load a MAD-X file into the current workspace."""
        with self.repo.filename(name) as f:
            self.madx.call(f, True)
        self.init_files.append(name)

    #----------------------------------------
    # Serialization
    #----------------------------------------

    # current version of model API
    API_VERSION = 1

    @classmethod
    def check_compatibility(cls, data):
        """
        Check a model definition for compatibility.

        :param dict data: a model definition to be tested
        :raises ValueError: if the model definition is incompatible
        """
        model_api = data.get('api_version', 'undefined')
        if model_api != cls.API_VERSION:
            raise ValueError(("Incompatible model API version: {!r},\n"
                              "              Required version: {!r}")
                             .format(model_api, cls.API_VERSION))

    # TODO: save reproducible state of workspace?
    def save(self, filename):
        """Save model to file."""
        data = self.model_data()
        text = yaml.safe_dump(data, default_flow_style=False)
        with open(filename, 'wt') as f:
            f.write(text)

    def model_data(self):
        """Return model data as dictionary."""
        return dict(self.data, **{
            'api_version': self.API_VERSION,
            'init-files': self.init_files,
            'sequence': self.seq_name,
            'range': list(self.range),
            'beam': self.beam,
            'twiss': self.twiss_args,
        })

    def load(self, filename):
        """Load model or plain MAD-X file."""
        self.utool = UnitConverter.from_config_dict(self.config['units'])
        path, name = os.path.split(filename)
        base, ext = os.path.splitext(name)
        self.repo = FileResource(path)
        self.madx = Madx(command_log=self.command_log, **self.minrpc_flags())
        self.name = base
        if ext.lower() in ('.yml', '.yaml'):
            self.load_model(name)
        else:
            self.load_madx_file(name)

    def load_model(self, filename):
        """Load model data from file."""
        self.data = data = self.repo.yaml(filename, encoding='utf-8')
        self.check_compatibility(data)
        self.repo = self.repo.get(data.get('path', '.'))
        self._load_params(data, 'beam')
        self._load_params(data, 'twiss')
        for filename in data.get('init-files', []):
            self.call(filename)
        segment_data = {'sequence', 'range', 'beam', 'twiss'}
        if all(data.get(p) for p in segment_data):
            self.init_segment(data)

    def load_madx_file(self, filename):
        """Load a plain MAD-X file."""
        self.call(filename)
        sequence = self._get_main_sequence()
        data = self._get_seq_model(sequence)
        self.init_segment(data)

    def init_segment(self, data):
        """Initialize model sequence/range."""
        self._init_segment(
            sequence=data['sequence'],
            range=data['range'],
            beam=data['beam'],
            twiss_args=data['twiss'],
        )

    def _get_main_sequence(self):
        """Try to guess the 'main' sequence to be viewed."""
        sequence = self.madx.active_sequence
        if sequence:
            return sequence.name
        sequences = self.madx.sequences
        if not sequences:
            raise ValueError("No sequences defined!")
        if len(sequences) != 1:
            # TODO: ask user which one to use
            raise ValueError("Multiple sequences defined, none active. Cannot uniquely determine which to use.")
        return next(iter(sequences))

    def _get_seq_model(self, sequence_name):
        """
        Return a model as good as possible from the last TWISS statement used
        for the given sequence, if available.

        Note that it seems currently not possible to reliably access prior
        TWISS statements and hence the information required to guess the
        model is extracted from the TWISS tables associated with the
        sequences. This means that

            - twiss tables may accidentally be associated with the wrong
              sequence
            - there is no reliable way to tell which parameters were set in
              the twiss command and hence deduce the correct (expected) model
            - you have to make sure the twiss range starts with a zero-width
              element (e.g. MARKER), otherwise TWISS parameters at the start
              of the range can not be reliably extrapolated

        The returned model should be seen as a first guess/approximation. Some
        fields may be empty if they cannot reliably be determined.

        :raises RuntimeError: if the sequence is undefined
        """
        try:
            sequence = self.madx.sequences[sequence_name]
        except KeyError:
            raise RuntimeError("The sequence is not defined.")
        try:
            beam = sequence.beam
        except RuntimeError:
            beam = {}
        try:
            range, twiss = self._get_twiss(sequence)
        except RuntimeError:
            range = (sequence_name+'$start', sequence_name+'$end')
            twiss = {}
        return {
            'sequence': sequence_name,
            'range': range,
            'beam': beam,
            'twiss': twiss,
        }

    def _get_twiss(self, sequence):
        """
        Try to determine (range, twiss) from the MAD-X state.

        :raises RuntimeError: if unable to make a useful guess
        """
        table = sequence.twiss_table        # raises RuntimeError
        try:
            first, last = table.range
        except ValueError:
            raise RuntimeError("TWISS table inaccessible or nonsensical.")
        if first not in sequence.expanded_elements or last not in sequence.expanded_elements:
            raise RuntimeError("The TWISS table appears to belong to a different sequence.")
        # TODO: this inefficiently copies over the whole table over the pipe
        # rather than just the first row.
        mandatory_fields = {'betx', 'bety', 'alfx', 'alfy'}
        optional_fields = {
            'x', 'px', 'mux', 'dx', 'dpx',
            'y', 'py', 'muy', 'dy', 'dpy',
            't', 'pt',
            'wx', 'phix', 'dmux', 'ddx', 'ddpx',
            'wy', 'phiy', 'dmuy', 'ddy', 'ddpy',
            'r11', 'r12', 'r21', 'r22',
            'tolerance', 'deltap',   # TODO: deltap has special format!
        }
        # TODO: periodic lines -> only mux/muy/deltap
        # TODO: logical parameters like CHROM
        twiss = {
            key: float(data[0])
            for key, data in table.items()
            if issubclass(data.dtype.type, np.number) and (
                    (key in mandatory_fields) or
                    (key in optional_fields and data[0] != 0)
            )
        }
        return (first, last), twiss

    _columns = [
        'name', 'l', 'angle', 'k1l',
        's',
        'x', 'y',
        'betx','bety',
        'alfx', 'alfy',
        'sig11', 'sig12', 'sig13', 'sig14', 'sig15', 'sig16',
        'sig21', 'sig22', 'sig23', 'sig24', 'sig25', 'sig26',
        'sig31', 'sig32', 'sig33', 'sig34', 'sig35', 'sig36',
        'sig41', 'sig42', 'sig43', 'sig44', 'sig45', 'sig46',
        'sig51', 'sig52', 'sig53', 'sig54', 'sig55', 'sig56',
        'sig61', 'sig62', 'sig63', 'sig64', 'sig65', 'sig66',
    ]

    def _init_segment(self, sequence, range, beam, twiss_args):
        """
        :param str sequence:
        :param tuple range:
        """

        self.sequence = self.madx.sequences[sequence]
        self.seq_name = self.sequence.name
        self.continuous_matching = True

        self._beam = beam
        self._twiss_args = twiss_args
        self._use_beam(beam)
        self.sequence.use()

        # Use `expanded_elements` rather than `elements` to have a one-to-one
        # correspondence with the data points of TWISS/SURVEY:
        make_element = partial(Element, self.madx, self.utool)
        self.el_names = self.sequence.expanded_element_names()
        self.elements = ElementList(self.el_names, make_element)
        self.positions = self.sequence.expanded_element_positions()

        self.start, self.stop = self.parse_range(range)
        self.range = (normalize_range_name(self.start.name),
                      normalize_range_name(self.stop.name))

        self.cache = {}

    def parse_range(self, range):
        """Convert a range str/tuple to a tuple of :class:`ElementInfo`."""
        if isinstance(range, str):
            range = range.split('/')
        start_name, stop_name = range
        return (self.get_element_info(start_name),
                self.get_element_info(stop_name))

    def get_init_ds(self):
        return SuperStore(OrderedDict([
            ('beam', MadxDataStore(self, 'beam')),
            ('twiss', MadxDataStore(self, 'twiss_args')),
        ]), utool=self.utool)

    def get_elem_ds(self, elem_index):
        return SuperStore(OrderedDict([
            ('attributes', ElementDataStore(self, 'element', elem_index=elem_index)),
        ]), utool=self.utool)

    # TODO…
    def _is_mutable_attribute(self, k, v):
        blacklist = self.config['parameter_sets']['element']['readonly']
        allowed_types = (list, number_types)
        return isinstance(v, allowed_types) and k.lower() not in blacklist

    # TODO: get data from MAD-X
    def get_twiss_args_raw(self):
        return self._twiss_args

    def set_twiss_args_raw(self, twiss):
        self._twiss_args = twiss

    # TODO: get data from MAD-X
    def get_beam_raw(self):
        """Get the beam parameter dictionary."""
        return self._beam

    def set_beam_raw(self, beam):
        """Set beam from a parameter dictionary."""
        self._beam = beam
        self._use_beam(beam)

    def update_beam(self, beam):
        new_beam = self._beam.copy()
        new_beam.update(
            (k.lower(), v)
            for k, v in self.utool.dict_strip_unit(beam).items())
        self.set_beam_raw(new_beam)
        self.twiss.invalidate()

    def update_twiss_args(self, twiss):
        new_twiss = self._twiss_args
        new_twiss.update(
            (k.lower(), v)
            for k, v in self.utool.dict_strip_unit(twiss).items())
        self.set_twiss_args_raw(new_twiss)
        self.twiss.invalidate()

    def update_element(self, data, elem_index):
        # TODO: this crashes for many parameters
        # - proper mutability detection
        # - update only changed values
        elem = self.elements[elem_index]
        name = elem['name']
        d = {k.lower(): v for k, v in data.items()
             if self._is_mutable_attribute(k, v)
             and elem[k.lower()] != v}
        d = self.utool.dict_strip_unit(d)
        if any(isinstance(v, (list,str)) for v in d.values()):
            self.madx.command(name, **d)
        else:
            # TODO: …KNL/KSL
            for k, v in d.items():
                # TODO: filter those with default values
                self.madx.set_value(_get_property_lval(elem, k), v)

        self.elements.invalidate(elem)
        self.twiss.invalidate()

    def _use_beam(self, beam):
        beam = dict(beam, sequence=self.sequence.name)
        self.madx.command.beam(**beam)

    def get_element_index(self, elem):
        """Get element index by it name."""
        return self.elements.index(elem)

    def get_twiss(self, elem, name, pos):
        """Return beam envelope at element."""
        ix = self.get_element_index(elem)

        s = self.get_twiss_column('s')
        y = self.get_twiss_column(name)
        x = self.indices[ix]

        # shortcut for thin elements:
        if self.utool.strip_unit('l', self.elements[ix].L) == 0:
            return y[x]

        lo = x.start-1 if x.start > 0 else x.start
        hi = x.stop+1

        from bisect import bisect_right
        i0 = bisect_right(s, pos, lo, hi)
        i1 = i0+1

        # never look outside the interpolation domain:
        if pos <= s[i0]: return y[i0]
        if pos >= s[i1]: return y[i1]

        dx = pos - s[i0]

        return y[i0] + dx * (y[i1]-y[i0]) / (s[i1]-s[i0])


    def contains(self, element):
        return (self.start.index <= element.index and
                self.stop.index >= element.index)

    def _get_twiss_args(self, **kwargs):
        twiss_init = self.utool.dict_strip_unit(self.twiss_args)
        twiss_args = {
            'sequence': self.sequence.name,
            'range': self.range,
            'columns': self._columns,
            'twiss_init': twiss_init,
        }
        twiss_args.update(kwargs)
        return twiss_args

    def get_transfer_maps(self, elems):
        """
        Get the transfer matrices R(i,j) between the given elements.

        This requires a full twiss call, so don't do it too often.
        """
        names = [self.get_element_info(el).name for el in elems]
        return self.madx.sectormap(names, **self._get_twiss_args())

    def survey(self):
        table = self.madx.survey()
        array = np.array([table[key] for key in FloorCoords._fields])
        return [FloorCoords(*row) for row in array.T]

    def ex(self):
        return self.summary['ex']

    def ey(self):
        return self.summary['ey']

    # curves

    def do_get_twiss_column(self, name):
        self.twiss.update()
        if name == 'envx':
            return self.utool.add_unit(name, self.get_twiss_column('sig11')**0.5)
        if name == 'envy':
            return self.utool.add_unit(name, self.get_twiss_column('sig33')**0.5)
        if name == 'posx':
            return self.get_twiss_column('x')
        if name == 'posy':
            return self.get_twiss_column('y')
        return self.utool.add_unit(name, self.madx.get_table('twiss')[name])

    def get_twiss_column(self, column):
        if column not in self.cache:
            self.cache[column] = self.do_get_twiss_column(column)
        return self.cache[column]

    @cachedproperty
    def native_graph_data(self):
        config = self.config
        styles = config['curve_style']
        return {
            info['name']: PlotInfo(
                name=info['name'],
                title=info['title'],
                curves=[
                    CurveInfo(
                        name=name,
                        short=name,
                        label=label,
                        style=style,
                        unit=from_config(unit))
                    for (name, unit, label), style in zip(info['curves'], styles)
                ])
            for info in config['graphs']
        }

    def get_native_graph_data(self, name, xlim):
        # TODO: use xlim for interpolate
        info = self.native_graph_data[name]
        xdata = self.get_twiss_column('s') + self.start.at
        data = {
            curve.short: np.vstack((xdata, ydata)).T
            for curve in info.curves
            for ydata in [self.get_twiss_column(curve.name)]
        }
        return info, data

    def get_native_graphs(self):
        """Get a list of curve names."""
        return {info.name: info.title
                for info in self.native_graph_data.values()}

    def _retrack(self):
        """Recalculate TWISS parameters."""
        self.cache.clear()
        self.madx.command.select(flag='interpolate', clear=True)
        self.madx.command.select(flag='interpolate', step=0.2)
        results = self.madx.twiss(**self._get_twiss_args())
        self.summary = self.utool.dict_add_unit(results.summary)

        # FIXME: this will fail if subsequent element have the same name.
        # Safer alternatives:
        # - do another twiss call without interpolate
        # - change the behaviour of MAD-X' interpolate option itself to make
        #   it clear in the table which rows are 'interpolated'
        # - change MAD-X interpolate option to produce 2 tables
        # - extract information via cpymad (table now has 'node' attribute)
        groups = itertools.groupby(enumerate(results['name']), lambda x: x[1])
        self.indices = [
            slice(l[0][0], l[-1][0])
            for k, v in groups
            for l in [list(v)]
        ]
        assert len(self.indices) == len(self.elements)

        # TODO: update elements

    def match(self, variables, constraints):

        # list intermediate positions
        # NOTE: need list instead of set, because quantity is unhashable:
        elem_positions = defaultdict(list)
        for elem, pos, axis, val in constraints:
            if pos not in elem_positions[elem['name']]:
                elem_positions[elem['name']].append(pos)
        elem_positions = {name: sorted(positions)
                          for name, positions in elem_positions.items()}

        # activate matching at specified positions
        self.madx.command.select(flag='interpolate', clear=True)
        for name, positions in elem_positions.items():
            at = self.elements[name]['at']
            l = self.elements[name]['l']
            if any(not isclose(p, at+l) for p in positions):
                x = [float((p-at)/l) for p in positions]
                self.madx.command.select(
                    flag='interpolate', range=name, at=x)

        # create constraints list to be passed to Madx.match
        madx_constraints = [
            {'range': elem['name'],
             'iindex': elem_positions[elem['name']].index(pos),
             axis: self.utool.strip_unit(axis, val)}
            for elem, pos, axis, val in constraints]

        weights = {
            'sig11': 1/self.utool.strip_unit('ex', self.ex()),
            'sig33': 1/self.utool.strip_unit('ey', self.ey()),
        }
        twiss_args = self.utool.dict_strip_unit(self.twiss_args)
        self.madx.match(sequence=self.sequence.name,
                        vary=variables,
                        constraints=madx_constraints,
                        weight=weights,
                        twiss_init=twiss_args)
        # TODO: update only modified elements
        self.elements.invalidate()
        self.twiss.invalidate()

    def read_monitor(self, name):
        """Mitigates read access to a monitor."""
        # TODO: handle split h-/v-monitor
        index = self.get_element_index(name)
        return {
            'envx': self.get_twiss_column('envx')[index],
            'envy': self.get_twiss_column('envy')[index],
            'posx': self.get_twiss_column('x')[index],
            'posy': self.get_twiss_column('y')[index],
        }

    def get_knob(self, elem, attr):
        try:
            expr = _get_property_lval(elem, attr)
        except IndexError:
            expr = None
        if expr is not None:
            return api.Knob(
                self, elem, attr, expr,
                self.utool._units.get(attr))

    def read_param(self, expr):
        return self.madx.evaluate(expr)

    def write_param(self, expr, value):
        self.madx.set_value(expr, value)
        self.twiss.invalidate()
        # TODO: invalidate element…
        # knob.elem.invalidate()


def process_spec(prespec, data):
    # TODO: Handle defaults for hard-coded and ad-hoc keys homogeniously.
    # The simplest option would be to simply specify list of priority keys in
    # the config file…
    spec = OrderedDict([
        (k, data.get(k, v))
        for item in prespec
        for spec in item.items()
        for k, v in process_spec_item(*spec)
        # TODO: distinguish items that are not in `data` (we can't just
        # filter, because that prevents editting defaulted parameters)
        # if k in data
    ])
    # Add keys that were not hard-coded in config:
    spec.update(OrderedDict([
        (k, v)
        for k, v in data.items()
        if k not in spec
    ]))
    return spec


class MadxDataStore(DataStore):

    def __init__(self, model, name, **kw):
        self.model = model
        self.utool = model.utool
        self.name = name
        self.label = name.title()
        self.data_key = name
        self.kw = kw
        self.conf = model.config['parameter_sets'][name]

    def _get(self):
        return getattr(self.model, self.name)

    def get(self):
        data = self._get()
        self.data = process_spec(self.conf['params'], data)
        return OrderedDict([
            (key.title(), val)
            for key, val in self.data.items()
        ])

    def update(self, values):
        return getattr(self.model, 'update_'+self.name)(values, **self.kw)

    # TODO: properly detect which items are mutable
    def mutable(self, key):
        return True

    def default(self, key):
        return self.data[key.lower()]


class Element(ElementBase):

    def invalidate(self, level=ElementBase.INVALIDATE_ALL):
        if level >= self.INVALIDATE_PARAM:
            self._merged = OrderedDict([
                ('name', self._name),
                ('el_id', self._idx),
            ])

    def _retrieve(self, name):
        if len(self._merged) == 2 and name not in self._merged:
            data = self._engine.active_sequence.expanded_elements[self._idx]
            self._merged.update(sort_to_top(data, [
                'Name',
                'Type',
                'At',
                'L',
                'Ksl',
                'Knl',
            ]))


class ElementDataStore(MadxDataStore):

    def _get(self):
        return self.model.elements[self.kw['elem_index']]

    def mutable(self, key):
        key = key.lower()
        return self.model._is_mutable_attribute(key, self.data[key])


# TODO: support expressions
def process_spec_item(key, value):
    if isinstance(value, list):
        rows = len(value)
        if rows > 0 and isinstance(value[0], list):
            cols = len(value[0])
            return [("{}{}{}".format(key, row+1, col+1), value[row][col])
                    for row in range(rows)
                    for col in range(cols)]
    return [(key, value)]


#----------------------------------------
# stuff for online control
#----------------------------------------

def _get_identifier(expr):
    if isinstance(expr, SymbolicValue):
        return str(expr._expression)
    elif isinstance(expr, Expression):
        return str(expr)
    else:
        return ''


# TODO: …KNL/KSL
def _get_property_lval(elem, attr):
    """
    Return lvalue name for a given element attribute from MAD-X.

    >>> get_element_attribute(elements['r1qs1'], 'k1')
    'r1qs1->k1'
    """
    expr = elem[attr]
    if not isinstance(expr, list):
        name = _get_identifier(expr)
        if is_identifier(name):
            return name
        return elem['name'] + '->' + attr
