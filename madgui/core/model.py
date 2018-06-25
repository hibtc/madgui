"""
MAD-X backend for madgui.
"""

import os
from collections import namedtuple, Sequence, OrderedDict, defaultdict, Mapping
from functools import partial, reduce
import itertools
from bisect import bisect_right
import subprocess
from threading import RLock
import re
from contextlib import contextmanager

import numpy as np

from cpymad.madx import Madx, AttrDict, ArrayAttribute, Command, Element
from cpymad.util import normalize_range_name, is_identifier

from madgui.core.base import Cache
from madgui.util.stream import AsyncReader
from madgui.util.undo import UndoCommand
from madgui.util import yaml


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
])

ElementInfo = namedtuple('ElementInfo', ['name', 'index', 'at'])
FloorCoords = namedtuple('FloorCoords', ['x', 'y', 'z', 'theta', 'phi', 'psi'])


class Madx(Madx):

    def __init__(self, *args, stdout_log, **kwargs):
        super().__init__(*args, **kwargs)
        self.reader = AsyncReader(self._process.stdout, stdout_log)
        self.reader.flush()

    _enter_count = 0
    _collected_cmds = None
    def input(self, text):
        if self._enter_count > 0:
            self._collected_cmds.append(text)
            return
        with self.reader:
            super().input(text)

    @contextmanager
    def transaction(self):
        self._enter_count += 1
        if self._enter_count == 1:
            self._collected_cmds = []
        try:
            yield None
        finally:
            self._enter_count -= 1
            if self._enter_count == 0:
                self.input(" ".join(self._collected_cmds))
                self._collected_cmds = None



class Model:

    """
    Contains the whole global state of a MAD-X instance and (possibly) loaded
    metadata.

    :ivar Madx madx: CPyMAD interpreter
    :ivar dict data: loaded model data
    :ivar str path: base folder
    """

    matcher = None

    def __init__(self, filename, config, command_log, stdout_log, undo_stack):
        super().__init__()
        self.twiss = Cache(self._retrack)
        self.sector = Cache(self._sector)
        self.twiss.invalidated.connect(self.sector.invalidate)
        self.data = {}
        self.path = None
        self.init_files = []
        self.command_log = command_log
        self.stdout_log = stdout_log
        self.undo_stack = undo_stack
        self.config = config
        self.filename = os.path.abspath(filename)
        path, name = os.path.split(filename)
        base, ext = os.path.splitext(name)
        self.path = path
        self.name = base
        self.madx = Madx(command_log=self.command_log,
                         stdout_log=self.stdout_log,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         lock=RLock())
        if ext.lower() in ('.yml', '.yaml'):
            with open(os.path.join(self.path, filename), 'rb') as f:
                self.data = data = yaml.safe_load(f)
            self.path = os.path.join(self.path, data.get('path', '.'))
            self._load_params(data, 'beam')
            self._load_params(data, 'twiss')
            for filename in data.get('init-files', []):
                self._call(filename)
        else:
            self._call(filename)
            sequence = self._guess_main_sequence()
            data = self._get_seq_model(sequence)
        self._init_segment(
            sequence=data['sequence'],
            range=data['range'],
            beam=data['beam'],
            twiss_args=data['twiss'],
        )
        self.twiss.invalidate()

    def destroy(self):
        """Annihilate current model. Stop interpreter."""
        if self.rpc_client:
            self.rpc_client.close()
        self.madx = None

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
            with open(os.path.join(self.path, vals), 'rb') as f:
                data[name] = yaml.safe_load(f)
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
        """Get the beam parameter dictionary."""
        return self._beam

    def set_beam(self, beam):
        """Set beam from a parameter dictionary."""
        self._beam = beam
        self._use_beam(beam)

    @property
    def globals(self):
        return self.madx.globals

    @globals.setter
    def globals(self, knobs):
        for k, v in knobs.items():
            self.madx.globals[k] = v

    beam = property(get_beam, set_beam)

    def get_element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        if pos is None:
            return None
        i0 = bisect_right(self.positions, pos)
        return self.elements[i0-1 if i0 > 0 else 0]

    def get_element_by_mouse_position(self, axes, pos):
        """Find an element close to the mouse cursor."""
        elem = self.get_element_by_position(pos)
        if elem is None:
            return None
        # Fuzzy select nearby elements, if they are <= 3px:
        at, L = elem.position, elem.length
        index = elem.index
        x0_px = axes.transData.transform_point((0, 0))[0]
        x2pix = lambda x: axes.transData.transform_point((x, 0))[0]-x0_px
        len_px = x2pix(L)
        if len_px > 5 or elem.base_name == 'drift':
            edge_px = max(1, min(2, round(0.2*len_px))) # max 2px cursor distance
            if index > 0 \
                    and x2pix(pos-at) < edge_px \
                    and x2pix(self.elements[index-1].length) <= 3:
                return self.elements[index-1]
            if index < len(self.elements) \
                    and x2pix(at+L-pos) < edge_px \
                    and x2pix(self.elements[index+1].length) <= 3:
                return self.elements[index+1]
        return elem

    def get_element_by_name(self, name):
        return self.elements[self.get_element_index(name)]

    def el_pos(self, el):
        """Position for matching / output."""
        return el.position + el.length

    continuous_matching = False

    def adjust_match_pos(self, el, pos):
        if not self.continuous_matching:
            return self.el_pos(el)
        at, l = el.position, el.length
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
        self.update_element({attr: value}, self.elements[elem].index)

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
        'sbend':        ['angle', 'k0'],
        'quadrupole':   ['k1', 'k1s'],
        'hkicker':      ['kick'],
        'vkicker':      ['kick'],
        'kicker':       ['hkick', 'vkick'],
        'solenoid':     ['ks'],
        'multipole':    ['knl', 'ksl'],
        'srotation':    ['angle'],
    }

    def get_elem_knobs(self, elem):
        return [
            knob
            for attr in self.ELEM_KNOBS.get(elem.base_name.lower(), ())
            if _is_property_defined(elem, attr)
            for knob in self._get_knobs(elem, attr)
        ]

    def get_knobs(self):
        """Get list of knobs."""
        return [
            knob
            for elem in self.elements
            for knob in self.get_elem_knobs(elem)
        ]

    @property
    def libmadx(self):
        """Access to the low level cpymad API."""
        return self.madx and self.madx._libmadx

    def call(self, name):
        old = self.globals.defs
        new = self._call(name)
        if new is None:
            # Have to clear the stack because general MAD-X commands are not
            # necessarily reversible (sequence definition, makethin, loading
            # tables, etc)!
            self.undo_stack.clear()
        else:
            text = "CALL {!r}".format(name)
            self._update(old, new, self._update_globals, text)
        self.elements.invalidate()
        self.twiss.invalidate()

    def load_strengths(self, name):
        new = read_strengths(name)
        if new is None:
            raise ValueError(
                "SyntaxError in {!r}. Not the simplest of .str files?"
                .format(name))
        self.update_globals(new)

    def _call(self, name):
        """Load a MAD-X file into the current workspace."""
        name = os.path.join(self.path, name)
        vals = read_strengths(name)
        self.madx.call(name, True)
        self.init_files.append(name)
        return vals

    #----------------------------------------
    # Serialization
    #----------------------------------------

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
            'init-files': self.init_files,
            'sequence': self.seq_name,
            'range': list(self.range),
            'beam': self.beam,
            'twiss': self.twiss_args,
        })

    def _guess_main_sequence(self):
        """Try to guess the 'main' sequence to be viewed."""
        sequence = self.madx.sequence()
        if sequence:
            return sequence.name
        sequences = self.madx.sequence
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
            sequence = self.madx.sequence[sequence_name]
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
            'beam': _eval_expr(beam),
            'twiss': _eval_expr(twiss),
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
            key: float(val)
            for key, val in table[0].items()
            if issubclass(val.dtype.type, np.number) and (
                    (key in mandatory_fields) or
                    (key in optional_fields and val != 0)
            )
        }
        return (first, last), twiss

    def _init_segment(self, sequence, range, beam, twiss_args):
        """
        :param str sequence:
        :param tuple range:
        """

        self.sequence = self.madx.sequence[sequence]
        self.seq_name = self.sequence.name
        self.continuous_matching = True

        self._beam = beam
        self.twiss_args = twiss_args
        self._use_beam(beam)
        self.sequence.use()

        # Use `expanded_elements` rather than `elements` to have a one-to-one
        # correspondence with the data points of TWISS/SURVEY:
        make_element = lambda index: Cache(partial(self._get_element, index))
        self.el_names = self.sequence.expanded_element_names()
        self.elements = ElementList(self.el_names, make_element)
        self.positions = self.sequence.expanded_element_positions()

        self.start, self.stop = self.parse_range(range)
        self.range = (normalize_range_name(self.start.name),
                      normalize_range_name(self.stop.name))

        self.cache = {}

    def _get_element(self, index):
        """Fetch the ``cpymad.madx.Element`` at the specified index in the
        current sequence."""
        elem = self.sequence.expanded_elements[index]
        if elem.base_name == 'sbend':
            # MAD-X uses the condition k0=0 to check whether the attribute
            # should be used (even though that means you can never have a kick
            # that exactly counteracts the bending angle):
            elem._attr['kick'] = elem.k0 and elem.k0 * elem.length - elem.angle
        return elem

    def parse_range(self, range):
        """Convert a range str/tuple to a tuple of :class:`ElementInfo`."""
        if isinstance(range, str):
            range = range.split('/')
        start_name, stop_name = range
        return (self.get_element_info(start_name),
                self.get_element_info(stop_name))

    def fetch_globals(self):
        return self._par_list(self.globals, 'globals', str.upper)

    def fetch_beam(self):
        from madgui.widget.params import ParamInfo
        beam = self.beam
        pars = self._par_list(beam, 'beam')
        ekin = (beam['energy'] - beam['mass']) / beam['mass']
        idx = next(i for i, p in enumerate(pars) if p.name.lower() == 'energy')
        pars.insert(idx, ParamInfo('E_kin', ekin))
        return pars

    def fetch_twiss(self):
        return self._par_list(self.twiss_args, 'twiss_args')

    def _par_list(self, data, name, title_transform=str.title, **kw):
        from madgui.widget.params import ParamInfo
        conf = self.config['parameter_sets'][name]
        data = process_spec(conf['params'], data)
        readonly = conf.get('readonly', ())
        return [ParamInfo(title_transform(key), val,
                          mutable=key not in readonly)
                for key, val in data.items()]

    # TODO…
    def _is_mutable_attribute(self, k, v):
        blacklist = self.config['parameter_sets']['element']['readonly']
        return k.lower() not in blacklist

    def _update(self, old, new, write, text):
        old = {k.lower(): v for k, v in items(old)}
        new = {k.lower(): v for k, v in items(new)}
        # NOTE: This trims not only expressions (as intended) but also regular
        # string arguments (which is incorrect). However, this should be a
        # sufficiently rare use case, so we don't care for now…
        _new = {k: v for k, v in items(new) if trim(old.get(k)) != trim(v)}
        _old = {k: v for k, v in items(old) if k in _new}
        _old.update({k: None for k in _new.keys() - _old.keys()})
        if _new:
            self._exec(UndoCommand(
                new, old, write, text.format(", ".join(_new))))

    def _exec(self, action):
        self.undo_stack.push(action)
        return action

    def update_globals(self, globals, text="Change knobs: {}"):
        return self._update(
            self.globals.defs, globals, self._update_globals, text)

    def update_beam(self, beam, text="Change beam: {}"):
        return self._update(
            self.beam, beam, self._update_beam, text)

    def update_twiss_args(self, twiss, text="Change twiss args: {}"):
        return self._update(
            self.twiss_args, twiss, self._update_twiss_args, text)

    def update_element(self, data, elem_index, text=None):
        elem = self.elements[elem_index]
        return self._update(
            elem.defs, data,
            partial(self._update_element, elem_index=elem_index),
            text or "Change element {}: {{}}".format(elem.name))

    def _update_globals(self, globals):
        with self.madx.transaction():
            for k, v in globals.items():
                if v is None:
                    v = 0
                elif v == '':
                    v = self.madx.globals[k]
                self.madx.globals[k] = v
        self.elements.invalidate()  # TODO: invalidate only elements that
                                    # depend on any of the updated variables?
        self.twiss.invalidate()

    def _update_beam(self, beam):
        new_beam = self.beam.copy()
        new_beam.update((k.lower(), v) for k, v in beam.items())
        if 'e_kin' in beam:
            eval = self.madx.eval
            ekin = eval(new_beam.get('e_kin'))
            mass = eval(new_beam.get('mass', 1))
            new_beam['energy'] = (ekin + 1) * mass
        new_beam.pop('e_kin', None)
        self.beam = new_beam
        self.twiss.invalidate()

    def _update_twiss_args(self, twiss):
        new_twiss = self.twiss_args.copy()
        new_twiss.update((k.lower(), v) for k, v in twiss.items())
        self.twiss_args = new_twiss
        self.twiss.invalidate()

    def _update_element(self, data, elem_index):
        # TODO: this crashes for many parameters
        # - proper mutability detection
        # - update only changed values
        elem = self.elements[elem_index]
        name = elem.node_name
        d = {k.lower(): v for k, v in data.items()
             if self._is_mutable_attribute(k, v)}
        if 'kick' in d and elem.base_name == 'sbend':
            # FIXME: This assumes the definition `k0:=(angle+k0)/l` and
            # will deliver incorrect results if this is not the case!
            var, = (set(self._get_knobs(elem, 'k0')) -
                    set(self._get_knobs(elem, 'angle')))
            self.madx.globals[var] = d.pop('kick')
        self.madx.elements[name](**d)

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
        if float(self.elements[ix].length) == 0:
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

    twiss_columns = [
        'alfx', 'alfy', 'betx', 'bety', 'gamx', 'gamy', 'ex', 'ey',
        'x', 'y', 'px', 'py', 'envx', 'envy',
    ]

    def get_elem_twiss(self, elem):
        ix = self.get_element_index(elem)
        i0 = self.indices[ix].stop
        return AttrDict({col: self.get_twiss_column(col)[i0]
                         for col in self.twiss_columns})

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
        twiss_args = {
            'sequence': self.sequence.name,
            'range': self.range,
        }
        twiss_args.update(self.twiss_args)
        twiss_args.update(kwargs)
        return twiss_args

    def sectormap(self, elem_from, elem_to=None, interval=None):
        """
        Return SECTORMAP|KICKS in the closed range [from,to] as 7x7 matrix.

        If only one parameter is given, return its transfer map.

        Elements can be specified by name or index.

        For a description of the ``interval`` parameter, see
        :meth:`~Model.get_transfer_maps`.
        """
        if elem_to is None: elem_to = elem_from
        if interval is None: interval = (0, 1)
        return self.get_transfer_maps([elem_from, elem_to], interval)[0]

    def get_transfer_maps(self, elems, interval=(1, 1)):
        """
        Get the transfer matrices R(i,j) between the given elements.

        The ``interval`` parameter can be used to select open/closedness of
        the individual intervals between the elements by adding offsets to the
        first and second element in every interval, counted from the entry
        end of the element.

        For example, by setting the ``interval`` parameter, the call
        ``get_transfer_maps([e0, e1, e2], interval)`` will retrieve the
        transfer maps in the following intervals:

        - ``interval=(0, 0)``  retrieves ``[e0, e1)`` and ``[e1, e2)``
        - ``interval=(0, 1)``  retrieves ``[e0, e1]`` and ``[e1, e2]``
        - ``interval=(1, 0)``  retrieves ``(e0, e1)`` and ``(e1, e2)``
        - ``interval=(1, 1)``  retrieves ``(e0, e1]`` and ``(e1, e2]``
        """
        maps = self.sector()
        indices = [self.get_element_info(el).index for el in elems]
        x0, x1 = interval
        return [
            reduce(lambda a, b: np.dot(b, a),
                   maps[max(0, i+x0):max(0, j+x1)], np.eye(7))
            for i, j in zip(indices, indices[1:])
        ]

    def survey(self):
        table = self.madx.survey()
        array = np.array([table[key] for key in FloorCoords._fields])
        return [FloorCoords(*row) for row in array.T]

    def ex(self):
        return self.summary.ex

    def ey(self):
        return self.summary.ey

    # curves

    def do_get_twiss_column(self, name):
        self.twiss()
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
        return self.twiss.data[name]

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
                    style=style)
                for (name, label), style in zip(conf['curves'], styles)
            ])

        xdata = self.get_twiss_column('s') + self.start.at
        data = {
            curve.short: (xdata, self.get_twiss_column(curve.name))
            for curve in info.curves
        }
        return info, data

    def get_graphs(self):
        """Get a list of graph names."""
        return {name: info['title']
                for name, info in self.config['graphs'].items()}

    def get_graph_columns(self):
        """Get a set of all columns used in any graph."""
        cols = {
            name
            for info in self.config['graphs'].values()
            for name, _ in info['curves']
        }
        cols.add('s')
        cols.update(self.cache.keys())
        return cols

    def _retrack(self):
        """Recalculate TWISS parameters."""
        self.cache.clear()
        step = self.sequence.elements[-1].position/400
        self.madx.command.select(flag='interpolate', clear=True)
        self.madx.command.select(flag='interpolate', step=step)
        results = self.madx.twiss(**self._get_twiss_args())
        self.summary = results.summary

        # FIXME: this will fail if subsequent element have the same name.
        # Safer alternatives:
        # - do another twiss call without interpolate
        # - change the behaviour of MAD-X' interpolate option itself to make
        #   it clear in the table which rows are 'interpolated'
        # - change MAD-X interpolate option to produce 2 tables
        # - extract information via cpymad (table now has 'node' attribute)
        groups = itertools.groupby(enumerate(results.name), lambda x: x[1])
        self.indices = [
            slice(l[0][0], l[-1][0])
            for k, v in groups
            for l in [list(v)]
        ]
        assert len(self.indices) == len(self.elements)
        return results

        # TODO: update elements

    def _sector(self):
        """Compute sectormaps of all elements."""
        # TODO: Ideally, we should compute sectormaps and twiss during the
        # same MAD-X TWISS command. But, since we don't need interpolated
        # sectormaps, this will require patching MAD-X first…
        self.madx.command.select(flag='interpolate', clear=True)
        # NOTE: we have to pass a different twiss table because madgui
        # currently fetches twiss columns only demand. Therefore, using the
        # same twiss table for both TWISS/SECTORMAP routines would lead to
        # inconsistent table lengths (interpolate vs no-interpolate!).
        return self.madx.sectormap((), table='sectortwiss', **self._get_twiss_args())

    def match(self, vary, constraints, **kwargs):

        # list intermediate positions
        # NOTE: need list instead of set, because quantity is unhashable:
        elem_positions = defaultdict(list)
        for elem, pos, axis, val in constraints:
            if pos not in elem_positions[elem.node_name]:
                elem_positions[elem.node_name].append(pos)
        elem_positions = {name: sorted(positions)
                          for name, positions in elem_positions.items()}

        # activate matching at specified positions
        self.madx.command.select(flag='interpolate', clear=True)
        for name, positions in elem_positions.items():
            at = self.elements[name].position
            l = self.elements[name].length
            positions = [at+l if p is None else p for p in positions]
            if any(not np.isclose(p, at+l) for p in positions):
                x = [float((p-at)/l) for p in positions]
                self.madx.command.select(
                    flag='interpolate', range=name, at=x)

        # create constraints list to be passed to Madx.match
        cons = {}
        for elem, pos, axis, val in constraints:
            key = (elem.node_name, elem_positions[elem.node_name].index(pos))
            cons.setdefault(key, {})[axis] = val
        madx_constraints = [
            dict(range=name, iindex=pos, **c)
            for (name, pos), c in cons.items()]

        # FIXME TODO: use position-dependent emittances…
        ex = self.ex()
        ey = self.ey()
        weights = {
            'sig11': 1/ex, 'sig12': 1/ex, 'sig21': 1/ex, 'sig22': 1/ex,
            'sig33': 1/ey, 'sig34': 1/ey, 'sig43': 1/ey, 'sig44': 1/ey,
        }
        weights.update(kwargs.pop('weight', {}))
        used_cols = {axis.lower() for elem, pos, axis, val in constraints}
        weights = {k: v for k, v in weights.items() if k in used_cols}
        twiss_args = self.twiss_args.copy()
        twiss_args.update(kwargs)

        old_values = {v: self.read_param(v) for v in vary}
        self.madx.match(sequence=self.sequence.name,
                        vary=vary,
                        constraints=madx_constraints,
                        weight=weights,
                        **twiss_args)
        new_values = {v: self.read_param(v) for v in vary}
        self._update(old_values, new_values, self._update_globals, "Match: {}")

        # return corrections
        return new_values

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

    def _get_knobs(self, elem, attr):
        """Return list of all knob names belonging to the given attribute."""
        try:
            expr, vars = _get_property_lval(elem, attr)
            return vars
        except IndexError:
            return []

    def read_param(self, expr):
        """Read element attribute. Return numeric value."""
        return self.madx.eval(expr)

    write_params = update_globals


def process_spec(prespec, data):
    # NOTE: we cast integers specified in the config to floats, in order to
    # get the correct ValueProxy in TableView. Technically, this makes it
    # impossible to specify a pure int parameter in the config file, but we
    # don't have any so far anyway… Note that we can't use `isinstance` here,
    # because that matches bool as well.
    float_ = lambda x: float(x) if type(x) is int else x
    # TODO: Handle defaults for hard-coded and ad-hoc keys homogeniously.
    # The simplest option would be to simply specify list of priority keys in
    # the config file…
    spec = OrderedDict([
        (k, float_(data.get(k, v)))
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


class ElementList(Sequence):

    """
    Immutable list of beam line elements.

    Each element is a dictionary containing its properties.
    """

    def __init__(self, el_names, Element):
        self._el_names = el_names
        self._indices = {n.lower(): i for i, n in enumerate(el_names)}
        self._elems = [Element(i) for i in range(len(el_names))]
        self.invalidate()

    def invalidate(self, elem=None):
        if elem is None:
            for elem in self._elems:
                elem.invalidate()
            beg, end = self[0], self[-1]
            self.min_x = beg.position
            self.max_x = end.position + end.length
        else:
            index = self.index(elem)
            self._elems[index].invalidate()

    def __contains__(self, element):
        """
        Check if sequence contains element with specified name.

        Can be invoked with the element index or name or the element itself.
        """
        try:
            self.index(element)
            return True
        except (KeyError, ValueError):
            return False

    def __getitem__(self, index):
        """Return element with specified index."""
        return self._elems[self.index(index)]()

    def __len__(self):
        """Get number of elements."""
        return len(self._el_names)

    def index(self, element):
        """
        Find index of element with specified name.

        Can be invoked with the element index or name or the element itself.

        :raises ValueError: if the element is not found
        """
        if isinstance(element, int):
            return element
        if isinstance(element, (Element, ElementInfo)):
            return element.index
        if isinstance(element, str):
            return self._index_by_name(element)
        raise ValueError("Unhandled type: {!r}", type(element))

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

def _get_property_lval(elem, attr):
    """
    Return knobs names for a given element attribute from MAD-X.

    >>> get_element_attribute(elements['r1qs1'], 'k1')
    ('r1qs1->k1', ['kL_R1QS1'])
    """
    expr = elem.cmdpar[attr].expr
    madx = elem._madx
    if isinstance(expr, list):
        vars = list(set.union(*(set(madx.expr_vars(e)) for e in expr if e)))
        if len(vars) == 1 and any(e == vars[0] for e in expr):
            name = vars[0]
        else:
            name = elem.node_name + '->' + attr
    else:
        expr = expr or ''
        name = expr if is_identifier(expr) else elem.node_name + '->' + attr
        vars = madx.expr_vars(expr) if expr else []
    return name, vars


def _is_property_defined(elem, attr):
    """Check if attribute of an element was defined."""
    while elem.parent is not elem:
        try:
            cmdpar = elem.cmdpar[attr]
            if cmdpar.inform:
                return bool(cmdpar.expr)
        except (KeyError, IndexError):
            pass
        elem = elem.parent
    return False


def _eval_expr(value):
    """Helper method that replaces :class:`Expression` by their values."""
    # NOTE: This method will become unnecessary in cpymad 1.0.
    if isinstance(value, list):
        return [_eval_expr(v) for v in value]
    if isinstance(value, (dict, Command)):
        return {k: _eval_expr(v) for k, v in value.items()}
    if isinstance(value, ArrayAttribute):
        return list(value)
    return value


def read_strengths(filename):
    """Read .str file, return as dict."""
    with open(filename) as f:
        try:
            return parse_strengths(f)
        except (ValueError, AttributeError):
            return None

def parse_strengths(lines):
    return dict(
        parse_line(line)
        for line in map(str.strip, lines)
        if line and not line.startswith('#')
    )

RE_ASSIGN = re.compile(r'^([a-z_][a-z0-9_]*)\s*:?=\s*(.*);$', re.IGNORECASE)

def parse_line(line):
    m = RE_ASSIGN.match(line)
    if not m:
        raise ValueError("not an assignment: {!r}".format(line))
    k, v = m.groups()
    try:
        return k, float(v)
    except ValueError:
        return k, v


def items(d):
    return d.items() if isinstance(d, Mapping) else d

def trim(s):
    return s.replace(' ', '') if isinstance(s, str) else s
