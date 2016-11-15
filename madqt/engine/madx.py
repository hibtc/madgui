# encoding: utf-8
"""
MAD-X backend for MadQt.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from six import string_types as basestring
import numpy as np
import yaml

from cpymad.madx import Madx
from cpymad.util import normalize_range_name, name_from_internal

from madqt.core.unit import from_config
from madqt.util.misc import attribute_alias, cachedproperty

from madqt.engine.common import (
    FloorCoords, ElementInfo, EngineBase, SegmentBase,
    PlotInfo, CurveInfo,
)


__all__ = [
    'ElementInfo',
    'Universe',
    'Segment',
]


class Universe(EngineBase):

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
        super(Universe, self).__init__(filename, app_config)

    @property
    def libmadx(self):
        """Access to the low level cpymad API."""
        return self.madx and self.madx._libmadx

    def call(self, name):
        """Load a MAD-X file into the current universe."""
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

    # TODO: save reproducible state of universe?
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

    def load_dispatch(self, name, ext):
        """Load model or plain MAD-X file."""
        self.madx = madx = Madx(**self.minrpc_flags())
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
            universe=self,
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
        if first not in sequence.elements or last not in sequence.elements:
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
    ]

    def __init__(self, universe, sequence, range, beam, twiss_args):
        """
        :param Universe universe:
        :param str sequence:
        :param tuple range:
        """

        super(Segment, self).__init__()

        self.universe = universe
        self.sequence = universe.madx.sequences[sequence]

        self.start, self.stop = self.parse_range(range)
        self.range = (normalize_range_name(self.start.name),
                      normalize_range_name(self.stop.name))

        self._beam = beam
        self._twiss_args = twiss_args
        self._use_beam(beam)

        self.raw_elements = self.sequence.elements
        # TODO: provide uncached version of elements with units:
        self.elements = list(map(
            self.utool.dict_add_unit, self.raw_elements))

        self.cache = {}
        self.retrack()

    @property
    def madx(self):
        return self.universe.madx

    def parse_range(self, range):
        """Convert a range str/tuple to a tuple of :class:`ElementInfo`."""
        if isinstance(range, basestring):
            range = range.split('/')
        start_name, stop_name = range
        return (self.get_element_info(start_name),
                self.get_element_info(stop_name))

    def get_beam_conf(self):
        conf = self.universe.config['parameter_sets']['beam']
        return (process_spec(conf['params']), self.beam, conf)

    def get_twiss_conf(self):
        conf = self.universe.config['parameter_sets']['twiss']
        return (process_spec(conf['params']), self.twiss_args, conf)

    def get_twiss_args_raw(self):
        return self._twiss_args

    def set_twiss_args_raw(self, twiss):
        self._twiss_args = twiss

    def get_beam_raw(self):
        """Get the beam parameter dictionary."""
        return self._beam

    def set_beam_raw(self, beam):
        """Set beam from a parameter dictionary."""
        self._beam = beam
        self._use_beam(beam)

    def _use_beam(self, beam):
        beam = dict(beam, sequence=self.sequence.name)
        self.madx.command.beam(**beam)

    def get_element_data_raw(self, elem):
        return self.universe.madx.active_sequence.elements[elem]

    def get_element_index(self, elem):
        """Get element index by it name."""
        return self.sequence.elements.index(elem)

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
        names = map(name_from_internal, table['name'])
        array = np.array([table[key] for key in FloorCoords._fields])
        return [FloorCoords(*row) for row in array.T]

    def survey_elements(self):
        return self.sequence.expanded_elements

    def ex(self):
        return self.summary['ex']

    def ey(self):
        return self.summary['ey']

    # curves

    def do_get_twiss_column(self, name):
        if name == 'envx':
            return (self.get_twiss_column('betx') * self.ex())**0.5
        if name == 'envy':
            return (self.get_twiss_column('bety') * self.ey())**0.5
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
        config = self.universe.config
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

    def get_native_graph_data(self, name):
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
        results = self.madx.twiss(**self._get_twiss_args())
        self.summary = self.utool.dict_add_unit(results.summary)
        self.updated.emit()


def process_spec(prespec):
    from madqt.widget.params import ParamSpec
    return [
        ParamSpec(k, v)
        for item in prespec
        for spec in item.items()
        for k, v in process_spec_item(*spec)
    ]


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
