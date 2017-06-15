# encoding: utf-8
"""
MAD-X backend for MadQt.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import os
from collections import OrderedDict

from six import string_types as basestring
import numpy as np

from cpymad.madx import Madx
from cpymad.util import normalize_range_name

from madqt.resource import yaml
from madqt.core.unit import from_config
from madqt.util.misc import (attribute_alias, cachedproperty, sort_to_top,
                             logfile_name)
from madqt.resource.file import FileResource
from madqt.util.datastore import DataStore, SuperStore

from madqt.engine.common import (
    FloorCoords, ElementInfo, EngineBase, SegmentBase,
    PlotInfo, CurveInfo, ElementList,
)


# stuff for online control:
import madqt.online.api as api
from cpymad.types import Expression
from cpymad.util import is_identifier
from madqt.util.symbol import SymbolicValue


__all__ = [
    'ElementInfo',
    'Workspace',
    'Segment',
]


class Workspace(EngineBase):

    """
    Contains the whole global state of a MAD-X instance and (possibly) loaded
    metadata.

    :ivar Madx madx: CPyMAD interpreter
    :ivar dict data: loaded model data
    :ivar Segment segment: active segment
    :ivar madqt.resource.ResourceProvider repo: resource provider
    :ivar utool: Unit conversion tool for MAD-X.
    """

    backend_libname = 'cpymad'
    backend_title = 'MAD-X'
    backend = attribute_alias('madx')

    def __init__(self, filename, app_config):
        self.data = {}
        self.segment = None
        self.repo = None
        self.init_files = []
        super(Workspace, self).__init__(filename, app_config)

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
        data = self.data.copy()
        if self.segment:
            data.update(self.segment.data)
        data.update({
            'api_version': self.API_VERSION,
            'init-files': self.init_files,
        })
        data['range'] = list(data['range'])
        return data

    def load(self, filename):
        """Load model or plain MAD-X file."""
        path, name = os.path.split(filename)
        base, ext = os.path.splitext(name)
        command_log = logfile_name(path, base, '.commands.madx')
        self.repo = FileResource(path)
        self.madx = Madx(command_log=command_log, **self.minrpc_flags())
        if ext in ('.yml', '.yaml'):
            self.load_model(name)
        else:
            self.load_madx_file(name)

    def load_model(self, filename):
        """Load model data from file."""
        self.data = data = self.repo.yaml(filename, encoding='utf-8')
        self.check_compatibility(data)
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
        """Create a segment."""
        self.segment = Segment(
            workspace=self,
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


class Segment(SegmentBase):

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
        'sig11', 'sig12', 'sig13', 'sig14', 'sig15', 'sig16',
        'sig21', 'sig22', 'sig23', 'sig24', 'sig25', 'sig26',
        'sig31', 'sig32', 'sig33', 'sig34', 'sig35', 'sig36',
        'sig41', 'sig42', 'sig43', 'sig44', 'sig45', 'sig46',
        'sig51', 'sig52', 'sig53', 'sig54', 'sig55', 'sig56',
        'sig61', 'sig62', 'sig63', 'sig64', 'sig65', 'sig66',
    ]

    def __init__(self, workspace, sequence, range, beam, twiss_args):
        """
        :param Workspace workspace:
        :param str sequence:
        :param tuple range:
        """

        super(Segment, self).__init__()

        self.workspace = workspace
        self.sequence = workspace.madx.sequences[sequence]

        self._beam = beam
        self._twiss_args = twiss_args
        self._use_beam(beam)
        self.sequence.use()

        # Use `expanded_elements` rather than `elements` to have a one-to-one
        # correspondence with the data points of TWISS/SURVEY:
        el_names = self.sequence.expanded_element_names()
        self.elements = ElementList(el_names, self.get_element_data)
        self.positions = self.sequence.expanded_element_positions()

        self.start, self.stop = self.parse_range(range)
        self.range = (normalize_range_name(self.start.name),
                      normalize_range_name(self.stop.name))

        self.cache = {}
        self.retrack()

    @property
    def madx(self):
        return self.workspace.madx

    def parse_range(self, range):
        """Convert a range str/tuple to a tuple of :class:`ElementInfo`."""
        if isinstance(range, basestring):
            range = range.split('/')
        start_name, stop_name = range
        return (self.get_element_info(start_name),
                self.get_element_info(stop_name))

    def get_init_ds(self):
        return SuperStore(OrderedDict([
            ('beam', MadxDataStore(self, 'beam')),
            ('twiss', MadxDataStore(self, 'twiss')),
        ]), utool=self.utool)

    def get_elem_ds(self, elem_index):
        return SuperStore(OrderedDict([
            ('attributes', ElementDataStore(self, 'element', elem_index=elem_index)),
        ]), utool=self.utool)

    # TODO…
    def _is_mutable_attribute(self, k, v):
        blacklist = self.workspace.config['parameter_sets']['element']['readonly']
        return isinstance(v, (int, list, float)) and k.lower() not in blacklist

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
        self.retrack()

    def update_twiss_args(self, twiss):
        new_twiss = self._twiss_args
        new_twiss.update(
            (k.lower(), v)
            for k, v in self.utool.dict_strip_unit(twiss).items())
        self.set_twiss_args_raw(new_twiss)
        self.retrack()

    update_twiss = update_twiss_args
    twiss = property(lambda self: self.twiss_args)

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
        if any(isinstance(v, (list,basestring)) for v in d.values()):
            self.madx.command(name, **d)
        else:
            for k, v in d.items():
                # TODO: filter those with default values
                self.madx.set_value(_get_property_lval(elem, k), v)

        self.elements.update(elem)
        self.retrack()

    def _use_beam(self, beam):
        beam = dict(beam, sequence=self.sequence.name)
        self.madx.command.beam(**beam)

    def get_element_data_raw(self, elem, which=None):
        data = self.workspace.madx.active_sequence.expanded_elements[elem]
        data['el_id'] = data['index']
        return sort_to_top(data, [
            'Name',
            'Type',
            'At',
            'L',
            'Ksl',
            'Knl',
        ])

    def get_element_index(self, elem):
        """Get element index by it name."""
        return self.elements.index(elem)

    def get_twiss(self, elem, name):
        """Return beam envelope at element."""
        element = self.get_element_info(elem)
        if not self.contains(element):
            return None
        return self.get_twiss_column(name)[element.index - self.start.index]

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

    def get_transfer_map(self, beg_elem, end_elem):
        """
        Get the transfer matrix R(i,j) between the two elements.

        This requires a full twiss call, so don't do it too often.
        """
        info = self.get_element_info
        twiss_args = self._get_twiss_args()
        twiss_args['range_'] = (info(beg_elem).name, info(end_elem).name)
        twiss_args['tw_range'] = twiss_args.pop('range')
        return self.madx.get_transfer_map_7d(**twiss_args)

    def survey(self):
        # NOTE: SURVEY includes auto-generated DRIFTs, but segment.elements
        # does not!
        table = self.madx.survey()
        array = np.array([table[key] for key in FloorCoords._fields])
        return [FloorCoords(*row) for row in array.T]

    def ex(self):
        return self.summary['ex']

    def ey(self):
        return self.summary['ey']

    # curves

    def do_get_twiss_column(self, name):
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
        config = self.workspace.config
        styles = config['curve_style']
        return {
            info['name']: PlotInfo(
                name=info['name'],
                short=info['name'],
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
        return {info.short: (info.name, info.title)
                for info in self.native_graph_data.values()}

    def retrack(self):
        """Recalculate TWISS parameters."""
        self.cache.clear()
        self.madx.command.select(flag='interpolate', clear=True)
        self.madx.command.select(flag='interpolate', step=0.2)
        results = self.madx.twiss(**self._get_twiss_args())
        self.summary = self.utool.dict_add_unit(results.summary)
        # TODO: update elements
        self.updated.emit()

    def can_match_at(self, elem):
        return not elem['name'].endswith('[0]')

    def match(self, variables, constraints):
        # create constraints list to be passed to Madx.match
        madx_constraints = [
            {'range': elem['name'],
             axis: self.utool.strip_unit(axis, val)}
            for elem, pos, axis, val in constraints]

        twiss_args = self.utool.dict_strip_unit(self.twiss_args)
        self.madx.match(sequence=self.sequence.name,
                        vary=variables,
                        constraints=madx_constraints,
                        twiss_init=twiss_args)
        # TODO: update only modified elements
        self.elements.update()
        self.retrack()

    def get_magnet(self, elem, conv):
        return MagnetBackend(self.madx, self.utool, elem, {
            key: _get_property_lval(elem, key)
            for key in conv.backend_keys
        })

    def get_monitor(self, elem):
        return MonitorBackend(self, elem)


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

    def __init__(self, segment, name, **kw):
        self.segment = segment
        self.utool = segment.utool
        self.name = name
        self.label = name.title()
        self.data_key = name
        self.kw = kw
        self.conf = segment.workspace.config['parameter_sets'][name]

    def _get(self):
        return getattr(self.segment, self.name)

    def get(self):
        data = self._get()
        self.data = process_spec(self.conf['params'], data)
        return OrderedDict([
            (key.title(), val)
            for key, val in self.data.items()
        ])

    def update(self, values):
        return getattr(self.segment, 'update_'+self.name)(values, **self.kw)

    # TODO: properly detect which items are mutable
    def mutable(self, key):
        return True

    def default(self, key):
        return self.data[key.lower()]


class ElementDataStore(MadxDataStore):

    def _get(self):
        return self.segment.elements[self.kw['elem_index']]

    def mutable(self, key):
        key = key.lower()
        return self.segment._is_mutable_attribute(key, self.data[key])


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


def _get_property_lval(elem, attr):
    """
    Return lvalue name for a given element attribute from MAD-X.

    >>> get_element_attribute(elements['r1qs1'], 'k1')
    'r1qs1->k1'
    """
    expr = elem[attr]
    if isinstance(expr, list):
        names = [_get_identifier(v) for v in expr]
        if not any(names):
            raise api.UnknownElement
        return names
    else:
        name = _get_identifier(expr)
        if is_identifier(name):
            return name
        return elem['name'] + '->' + attr


def _value(v):
    if isinstance(v, list):
        return [_value(x) for x in v]
    try:
        return v.value
    except AttributeError:
        return v

def _evaluate(madx, v):
    if isinstance(v, list):
        return [madx.evaluate(x) for x in v]
    return madx.evaluate(v)


class MagnetBackend(api.ElementBackend):

    """Mitigates r/w access to the properties of an element."""

    def __init__(self, madx, utool, elem, lval):
        self._madx = madx
        self._lval = lval
        self._elem = elem
        self._utool = utool

    def get(self):
        """Get dict of values from MAD-X."""
        return {key: self._utool.add_unit(key, _evaluate(self._madx, lval))
                for key, lval in self._lval.items()}

    def set(self, values):
        """Store values to MAD-X."""
        # TODO: update cache
        madx = self._madx
        for key, val in values.items():
            plain_value = self._utool.strip_unit(key, val)
            lval = self._lval[key]
            if isinstance(val, list):
                for k, v in zip(lval, plain_value):
                    if k:
                        madx.set_value(k, v)
            else:
                madx.set_value(lval, plain_value)


class MonitorBackend(api.ElementBackend):

    """Mitigates read access to a monitor."""

    # TODO: handle split h-/v-monitor

    def __init__(self, segment, element):
        self._segment = segment
        self._element = element

    def get(self, values):
        twiss = self._segment.tw
        index = self._segment.get_element_index(self._element)
        return {
            'betx': twiss['betx'][index],
            'bety': twiss['bety'][index],
            'x': twiss['posx'][index],
            'y': twiss['posy'][index],
        }

    def set(self, values):
        raise NotImplementedError("Can't set TWISS: monitors are read-only!")

