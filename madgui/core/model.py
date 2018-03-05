"""
MAD-X backend for madgui.
"""

import os
import re
from collections import namedtuple, Sequence, Mapping, OrderedDict, defaultdict
from functools import partial
import itertools
import logging
from bisect import bisect_right
import subprocess
from threading import RLock

import numpy as np

from cpymad.madx import Madx
from cpymad.util import normalize_range_name

from madgui.core.base import Object, Signal, Cache
from madgui.resource import yaml
from madgui.core.unit import (UnitConverter, from_config, isclose,
                              number_types, strip_unit)
from madgui.resource.file import FileResource
from madgui.util.datastore import DataStore


# stuff for online control:
import madgui.online.api as api
from cpymad.types import Expression
from cpymad.util import is_identifier
from madgui.util.symbol import SymbolicValue


__all__ = [
    'ElementInfo',
    'Model',
]


PlotInfo = namedtuple('PlotInfo', [
    'name',     # internal graph id (e.g. 'beta.g')
    'title',    # long display name ('Beta function')
    'curves',   # [CurveInfo]
])

CurveInfo = namedtuple('CurveInfo', [
    'name',     # internal curve id (e.g. 'beta.g.a')
    'short',    # display name for statusbar ('beta_a')
    'label',    # y-axis/legend label ('$\beta_a$')
    'style',    # **kwargs for ax.plot
    'unit',     # y unit
])

ElementInfo = namedtuple('ElementInfo', ['name', 'index', 'at'])
FloorCoords = namedtuple('FloorCoords', ['x', 'y', 'z', 'theta', 'phi', 'psi'])


class Model(Object):

    """
    Contains the whole global state of a MAD-X instance and (possibly) loaded
    metadata.

    :ivar Madx madx: CPyMAD interpreter
    :ivar dict data: loaded model data
    :ivar madgui.resource.ResourceProvider repo: resource provider
    :ivar utool: Unit conversion tool for MAD-X.
    """

    backend_libname = 'cpymad'
    backend_title = 'MAD-X'

    destroyed = Signal()
    matcher = None

    def __init__(self, filename, config, command_log):
        super().__init__()
        self.twiss = Cache(self._retrack)
        self.log = logging.getLogger(__name__)
        self.data = {}
        self.repo = None
        self.init_files = []
        self.command_log = command_log
        self.config = config
        self.load(filename)
        self.twiss.invalidate()

    def minrpc_flags(self):
        """Flags for launching the backend library in a remote process."""
        return dict(lock=RLock(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def destroy(self):
        """Annihilate current model. Stop interpreter."""
        if self.rpc_client:
            self.rpc_client.close()
        self.madx = None
        self.destroyed.emit()

    @property
    def rpc_client(self):
        """Low level RPC client."""
        return self.madx and self.madx._service

    @property
    def remote_process(self):
        """Backend process."""
        return self.madx and self.madx._process

    def _load_params(self, data, name):
        """Load parameter dict from file if necessary."""
        vals = data.get(name, {})
        if isinstance(vals, str):
            data[name] = self.repo.yaml(vals, encoding='utf-8')
            if len(data[name]) == 1 and name in data[name]:
                data[name] = data[name][name]

    def get_element_info(self, element):
        """Get :class:`ElementInfo` from element name or index."""
        if isinstance(element, ElementInfo):
            return element
        if isinstance(element, str):
            element = self.get_element_index(element)
        if element < 0:
            element += len(self.elements)
        name = self.el_names[element]
        pos = self.positions[element]
        return ElementInfo(name, element, pos)

    def get_beam(self):
        return self.utool.dict_add_unit(self.get_beam_raw())

    def set_beam(self, beam):
        self.set_beam_raw(self.utool.dict_strip_unit(beam))

    def get_twiss_args(self):
        return self.utool.dict_add_unit(self.get_twiss_args_raw())

    def set_twiss_args(self, twiss):
        self.set_twiss_args_raw(self.utool.dict_strip_unit(twiss))

    def get_globals(self):
        blacklist = ('none', 'twiss_tol', 'degree')
        return {k: v for k, v in self.madx.globals.items()
                if k not in blacklist}

    def set_globals(self, knobs):
        for k, v in knobs.items():
            self.madx.globals[k] = v

    globals = property(get_globals, set_globals)
    beam = property(get_beam, set_beam)
    twiss_args = property(get_twiss_args, set_twiss_args)

    def get_element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        if pos is None:
            return None
        val = self.utool.strip_unit('s', pos)
        i0 = bisect_right(self.positions, val)
        return self.elements[i0-1 if i0 > 0 else 0]

    def get_element_by_mouse_position(self, axes, pos):
        """Find an element close to the mouse cursor."""
        elem = self.get_element_by_position(pos)
        if elem is None:
            return None
        # Fuzzy select nearby elements, if they are <= 3px:
        at, L = elem.At, elem.L
        el_id = elem.El_id
        x0_px = axes.transData.transform_point((0, 0))[0]
        strip = lambda x: self.utool.strip_unit('at', x)
        x2pix = lambda x: axes.transData.transform_point((strip(x), 0))[0]-x0_px
        len_px = x2pix(L)
        pos_px = x2pix(pos)
        if len_px > 5 or elem.Type == 'drift':
            edge_px = max(1, min(2, round(0.2*len_px))) # max 2px cursor distance
            if el_id > 0 \
                    and x2pix(pos-at) < edge_px \
                    and x2pix(self.elements[el_id-1].L) <= 3:
                return self.elements[el_id-1]
            if el_id < len(self.elements) \
                    and x2pix(at+L-pos) < edge_px \
                    and x2pix(self.elements[el_id+1].L) <= 3:
                return self.elements[el_id+1]
        return elem

    def get_element_by_name(self, name):
        return self.elements[self.get_element_index(name)]

    def el_pos(self, el):
        """Position for matching / output."""
        return el.At + el.L

    continuous_matching = False

    def adjust_match_pos(self, el, pos):
        if not self.continuous_matching:
            return self.el_pos(el)
        at, l = el.At, el.L
        if pos <= at:   return at
        if pos >= at+l: return at+l
        return pos

    def get_best_match_pos(self, pos):
        """Find optics element by longitudinal position."""
        return min([
            (el, self.adjust_match_pos(el, pos))
            for el in self.elements
            if self.can_match_at(el)
        ], key=lambda x: abs(x[1]-pos))

    def can_match_at(self, element):
        return True

    def set_element_attribute(self, elem, attr, value):
        elem = self.elements[elem].El_id
        self.get_elem_ds(elem).update({
            attr: value,
        })

    # curves

    @property
    def curve_style(self):
        return self.config['line_view']['curve_style']

    def get_matcher(self):
        if self.matcher is None:
            # TODO: create MatchDialog
            from madgui.correct.match import Matcher
            self.matcher = Matcher(self, self.config['matching'])
        return self.matcher

    ELEM_KNOBS = {
        'sbend':        ['angle'],
        'quadrupole':   ['k1', 'k1s'],
        'hkicker':      ['kick'],
        'vkicker':      ['kick'],
        'kicker':       ['hkick', 'vkick'],
        'solenoid':     ['ks'],
        'multipole':    ['knl[0]', 'knl[1]', 'knl[2]', 'knl[3]',
                         'ksl[0]', 'ksl[1]', 'ksl[2]', 'ksl[3]'],
        'srotation':    ['angle'],
    }

    def get_knobs(self):
        """Get list of knobs."""
        return [
            knob
            for elem in self.elements
            for attr in self._get_attrs(elem)
            for knob in [self.get_knob(elem, attr)]
            if knob
        ]

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
        self.filename = filename
        self.utool = UnitConverter.from_config_dict(self.config['madx_units'])
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

    def get_globals_ds(self):
        return MadxDataStore(self, 'globals')

    def get_beam_ds(self):
        return MadxDataStore(self, 'beam')

    def get_twiss_ds(self):
        return MadxDataStore(self, 'twiss_args')

    def get_elem_ds(self, elem_index):
        return ElementDataStore(
            self, 'element', elem_index=elem_index)

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

    def update_globals(self, globals):
        self.set_globals(globals)
        self.twiss.invalidate()

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
        name = elem.Name
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

        i0 = bisect_right(s, pos, lo, hi)
        i1 = i0+1

        # never look outside the interpolation domain:
        if pos <= s[i0]: return y[i0]
        if pos >= s[i1]: return y[i1]

        dx = pos - s[i0]

        return y[i0] + dx * (y[i1]-y[i0]) / (s[i1]-s[i0])

    def get_elem_twiss(self, elem):
        ix = self.get_element_index(elem)
        i0 = self.indices[ix].stop
        return {
            'alfx': self.get_twiss_column('alfx')[i0],
            'alfy': self.get_twiss_column('alfy')[i0],
            'betx': self.get_twiss_column('betx')[i0],
            'bety': self.get_twiss_column('bety')[i0],
            'gamx': self.get_twiss_column('gamx')[i0],
            'gamy': self.get_twiss_column('gamy')[i0],
            'ex': self.get_twiss_column('ex')[i0],
            'ey': self.get_twiss_column('ey')[i0],
        }

    def get_elem_sigma(self, elem):
        ix = self.get_element_index(elem)
        i0 = self.indices[ix].stop
        return {
            sig_ij: self.get_twiss_column(sig_ij)[i0]
            for i, j in itertools.product(range(6), range(6))
            for sig_ij in ['sig{}{}'.format(i+1, j+1)]
        }

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
        col = self.get_twiss_column
        if name == 'alfx': return -col('sig12') / col('ex')
        if name == 'alfy': return -col('sig34') / col('ey')
        if name == 'betx': return +col('sig11') / col('ex')
        if name == 'bety': return +col('sig33') / col('ey')
        if name == 'gamx': return +col('sig22') / col('ex')
        if name == 'gamy': return +col('sig44') / col('ey')
        if name == 'envx': return col('sig11')**0.5
        if name == 'envy': return col('sig33')**0.5
        if name == 'posx': return col('x')
        if name == 'posy': return col('y')
        if name == 'ex': return (col('sig11') * col('sig22') -
                                 col('sig12') * col('sig21'))**0.5
        if name == 'ey': return (col('sig33') * col('sig44') -
                                 col('sig34') * col('sig43'))**0.5
        return self.utool.add_unit(name, self.twiss.data[name])

    def get_twiss_column(self, column):
        if column not in self.cache:
            self.cache[column] = self.do_get_twiss_column(column)
        return self.cache[column]

    def get_graph_data(self, name, xlim):
        """Get the data for a particular graph."""
        # TODO: use xlim for interpolate

        styles = self.config['line_view']['curve_style']
        conf = self.config['graphs'][name]
        info = PlotInfo(
            name=name,
            title=conf['title'],
            curves=[
                CurveInfo(
                    name=name,
                    short=name,
                    label=label,
                    style=style,
                    unit=from_config(unit))
                for (name, unit, label), style in zip(conf['curves'], styles)
            ])

        xdata = self.get_twiss_column('s') + self.start.at
        data = {
            curve.short: np.vstack((xdata, ydata)).T
            for curve in info.curves
            for ydata in [strip_unit(self.get_twiss_column(curve.name), curve.unit)]
        }
        return info, data

    def get_graphs(self):
        """Get a list of graph names."""
        return {name: info['title']
                for name, info in self.config['graphs'].items()}

    def _retrack(self):
        """Recalculate TWISS parameters."""
        self.cache.clear()
        step = self.sequence.elements[-1]['at']/400
        self.madx.command.select(flag='interpolate', clear=True)
        self.madx.command.select(flag='interpolate', step=step)
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
        return results

        # TODO: update elements

    def match(self, variables, constraints):

        # list intermediate positions
        # NOTE: need list instead of set, because quantity is unhashable:
        elem_positions = defaultdict(list)
        for elem, pos, axis, val in constraints:
            if pos not in elem_positions[elem.Name]:
                elem_positions[elem.Name].append(pos)
        elem_positions = {name: sorted(positions)
                          for name, positions in elem_positions.items()}

        # activate matching at specified positions
        self.madx.command.select(flag='interpolate', clear=True)
        for name, positions in elem_positions.items():
            at = self.elements[name].At
            l = self.elements[name].L
            if any(not isclose(p, at+l) for p in positions):
                x = [float((p-at)/l) for p in positions]
                self.madx.command.select(
                    flag='interpolate', range=name, at=x)

        # create constraints list to be passed to Madx.match
        madx_constraints = [
            {'range': elem.Name,
             'iindex': elem_positions[elem.Name].index(pos),
             axis: self.utool.strip_unit(axis, val)}
            for elem, pos, axis, val in constraints]

        # FIXME TODO: use position-dependent emittances…
        ex = self.utool.strip_unit('ex', self.ex())
        ey = self.utool.strip_unit('ey', self.ey())
        weights = {
            'sig11': 1/ex, 'sig12': 1/ex, 'sig21': 1/ex, 'sig22': 1/ex,
            'sig33': 1/ey, 'sig34': 1/ey, 'sig43': 1/ey, 'sig44': 1/ey,
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

    def _get_attrs(self, elem):
        attrs = self.ELEM_KNOBS.get(elem.Type.lower(), ())
        defd = [attr for attr in attrs if _is_property_defined(elem, attr)]
        return defd or attrs[:1]


    def get_knob(self, elem, attr):
        """Return a :class:`Knob` belonging to the given attribute."""
        try:
            expr = _get_property_lval(elem, attr)
        except IndexError:
            expr = None
        if expr is not None:
            return api.Knob(
                self, elem, attr, expr,
                self.utool._units.get(attr))

    def read_param(self, expr):
        """Read element attribute. Return numeric value. No units!"""
        return self.madx.evaluate(expr)

    def write_param(self, expr, value):
        """Update element attribute into control system. No units!"""
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
        if not self.valid():
            return OrderedDict()
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

    def valid(self):
        return True


class ElementList(Sequence):

    """
    Immutable list of beam line elements.

    Each element is a dictionary containing its properties.
    """

    def __init__(self, el_names, Element):
        self._el_names = el_names
        self._indices = {n.lower(): i for i, n in enumerate(el_names)}
        self._elems = [Element(i, n) for i, n in enumerate(el_names)]
        self.invalidate()

    def invalidate(self, elem=None):
        if elem is None:
            for elem in self._elems:
                elem.invalidate()
            beg, end = self[0], self[-1]
            self.min_x = beg.At
            self.max_x = end.At + end.L
        else:
            index = self.index(elem)
            self._elems[index].invalidate()

    def bound_x(self, x_value):
        return min(self.max_x, max(self.min_x, x_value))

    def bound_range(self, xlim):
        return tuple(map(self.bound_x, xlim))

    def __contains__(self, element):
        """
        Check if sequence contains element with specified name.

        Can be invoked with either the element dict or the element name.
        """
        try:
            self.index(element)
            return True
        except ValueError:
            return False

    def __getitem__(self, index):
        """Return element with specified index."""
        # allow element dicts/names to be passed for convenience:
        if isinstance(index, int):
            return self._get_by_index(index)
        if isinstance(index, (dict, Element)):
            return self._get_by_dict(index)
        if isinstance(index, ElementInfo):
            return self._get_by_dict({
                'name': index.name,
                'el_id': index.index,
            })
        if isinstance(index, str):
            return self._get_by_name(index)
        raise TypeError("Unhandled type: {!r}", type(index))

    def __len__(self):
        """Get number of elements."""
        return len(self._el_names)

    def index(self, element):
        """
        Find index of element with specified name.

        Can be invoked with either the element dict or the element name.

        :raises ValueError: if the element is not found
        """
        if isinstance(element, int):
            return element
        if isinstance(element, (dict, Element)):
            return self._index_by_dict(element)
        if isinstance(element, ElementInfo):
            return self._index_by_dict({
                'name': element.name,
                'el_id': element.index,
            })
        if isinstance(element, str):
            return self._index_by_name(element)
        raise ValueError("Unhandled type: {!r}", type(element))

    # TODO: remove?
    def _get_by_dict(self, elem):
        if 'el_id' not in elem:
            raise TypeError("Not an element dict: {!r}".format(elem))
        index = elem.El_id
        data = self._get_by_index(index)
        if elem.Name != data.Name:
            raise ValueError("Element name mismatch: expected {}, got {}."
                             .format(data.Name, elem.Name))
        return data

    def _get_by_name(self, name):
        index = self._index_by_name(name)
        return self._get_by_index(index)

    def _get_by_index(self, index):
        # Support a range of [-len, len-1] similar to builtin lists:
        return self._elems[index]

    # TODO: remove
    def _index_by_dict(self, elem):
        if 'el_id' not in elem:
            raise TypeError("Not an element dict: {!r}".format(elem))
        index = elem.El_id
        if elem.Name.lower() != self._el_names[index].lower():
            raise ValueError("Element name mismatch: expected {}, got {}."
                             .format(self._el_names[index], elem.Name))
        return index

    def _index_by_name(self, name):
        # TODO: warning – names do not always uniquely identify elements:
        #       auto-generated DRIFTs in MAD-X.
        name = name.lower()
        if len(self) != 0:
            if name in ('#s', 'beginning'):
                return 0
            elif name in ('#e', 'end'):
                return len(self) - 1
        return self._indices[name]


class Element(Mapping):

    """
    Dict-like base class for elements. Provides attribute access to properties
    by title case attribute names.

    Subclasses must implement ``_retrieve`` and ``invalidate``.
    """

    # Do not rely on the numeric values, they may be replaced by flags!
    INVALIDATE_TWISS = 0
    INVALIDATE_PARAM = 1
    INVALIDATE_ALL   = 2

    def __init__(self, model, utool, idx, name):
        self._model = model
        self._utool = utool
        self._idx = idx
        self._name = name.lower()
        self.invalidate(self.INVALIDATE_ALL)

    def __getitem__(self, name):
        # handle direct access to array elements, e.g. "knl[0]":
        if name.endswith(']'):
            head, tail = name.split('[', 1)
            index = int(tail[:-1])
            return self._get_field(head, index)
        self._retrieve(name)
        return self._utool.add_unit(name, self._merged[name])

    def __iter__(self):
        self._retrieve(None)
        return iter(self._merged)

    def __len__(self):
        self._retrieve(None)
        return len(self._merged)

    def _get_field(self, name, index):
        return self[name][index]

    _RE_ATTR = re.compile(r'^[A-Z][A-Za-z0-9_]*$')

    def __getattr__(self, name):
        """
        Provide attribute access to element properties.

        Attribute names must start with capital letter, e.g. Name, K1, KNL.
        """
        if not self._RE_ATTR.match(name):
            raise AttributeError(name)
        try:
            return self[name.lower()]
        except KeyError:
            raise AttributeError(name)

    def invalidate(self, level=INVALIDATE_ALL):
        """Invalidate cached data at and below the given level."""
        if level >= self.INVALIDATE_PARAM:
            self._merged = OrderedDict([
                ('name', self._name),
                ('el_id', self._idx),
            ])

    def _retrieve(self, name):
        """Retrieve data for key if possible; everything if None."""
        if len(self._merged) == 2 and name not in self._merged:
            data = self._model.active_sequence.expanded_elements[self._idx]
            self._merged.update(data)


class ElementDataStore(MadxDataStore):

    def _get(self):
        return self.model.elements[self.kw['elem_index']]

    def mutable(self, key):
        key = key.lower()
        return self.model._is_mutable_attribute(key, self.data[key])

    def valid(self):
        return 'elem_index' in self.kw


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
        return elem.Name + '->' + attr


def _is_property_defined(elem, attr):
    """Check if attribute of an element was defined."""
    try:
        value = elem.get(attr)
        return hasattr(value, '_expression') or float(value) != 0
    except (ValueError, TypeError, IndexError):
        return False
