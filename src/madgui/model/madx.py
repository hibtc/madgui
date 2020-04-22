"""
MAD-X backend for madgui.
"""

__all__ = [
    'Model',
    'reverse_sequence',
    'reverse_sequence_inplace',
    'TwissTable',
    '_guess_main_sequence',
    '_get_seq_model',
    '_get_twiss',
]

import os
from collections import defaultdict
from collections.abc import Mapping
from functools import partial, reduce
import itertools
from bisect import bisect_right
from contextlib import suppress
import logging
from numbers import Number

import numpy as np

from cpymad.madx import (
    Madx, AttrDict, ArrayAttribute, Command, Table, ExpandedElementList)
from cpymad.util import normalize_range_name
from cpymad.types import VAR_TYPE_DIRECT, VAR_TYPE_DEFERRED

from madgui.util.undo import UndoCommand
from madgui.util import yaml
from madgui.util.export import read_str_file, import_params
from madgui.util.misc import memoize, invalidate
from madgui.util.signal import Signal


class Model:

    """
    Contains the whole global state of a MAD-X instance and (possibly) loaded
    metadata.

    :ivar Madx madx: CPyMAD interpreter
    :ivar dict Model.data: loaded model data
    :ivar str path: base folder
    """

    updated = Signal()

    def __init__(self, madx, data, *, filename=None, undo_stack=None,
                 interpolate=0):
        super().__init__()
        self.madx = madx
        self.data = data
        self.filename = filename and os.path.abspath(filename)
        self.path, self.name = filename and os.path.split(filename)
        self.undo_stack = undo_stack
        if undo_stack:
            self.undo_stack.model = self
        self._init_segment(
            sequence=data['sequence'],
            range=data['range'],
            beam=data['beam'],
            twiss_args=data['twiss'],
        )
        self.interpolate = interpolate
        self.invalidate()

    def invalidate(self):
        """Invalidate twiss and sectormap computations. Initiate
        recomputation."""
        invalidate(self, 'twiss')
        invalidate(self, 'sector')
        invalidate(self, 'survey')
        self.updated.emit()

    @classmethod
    def load_file(cls, filename, madx=None, *,
                  undo_stack=None, interpolate=0, **madx_kwargs):
        """Load model from .madx or .yml file and pass additional arguments
        to the Model constructor."""
        madx = madx or Madx(**madx_kwargs)
        madx.option(echo=False)
        filename = os.path.abspath(filename)
        path, name = os.path.split(filename)
        ext = os.path.splitext(name)[1].lower()
        if ext in ('.yml', '.yaml'):
            data = yaml.load_file(filename)
            path = os.path.join(path, data.get('path', '.'))
            _load_params(data, 'beam', path)
            _load_params(data, 'twiss', path)
            for fname in data.get('init-files', []):
                _call(madx, path, fname)
        else:
            _call(madx, path, filename)
            seqname = _guess_main_sequence(madx)
            data = _get_seq_model(madx, seqname)
            data['init-files'] = [filename]
        return cls(
            madx, data,
            undo_stack=undo_stack,
            filename=filename,
            interpolate=interpolate)

    def __del__(self):
        self.destroy()

    def destroy(self):
        """Annihilate current model. Stop interpreter."""
        if self.madx is not None:
            with suppress(AttributeError, RuntimeError):
                self.madx._libmadx.finish()
            with suppress(AttributeError, RuntimeError):
                self.madx._service.close()
            with suppress(AttributeError, RuntimeError):
                self.madx._process.wait()
        self.madx = None

    @property
    def twiss_args(self) -> dict:
        """Return the dictionary of parameters for the MAD-X TWISS command."""
        return self._twiss_args

    @property
    def beam(self) -> dict:
        """Get the beam parameter dictionary."""
        return self._beam

    @property
    def globals(self) -> dict:
        """Return dict-like global variables."""
        return self.madx.globals

    def get_element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        if pos is None:
            return None
        i0 = bisect_right(self.positions, pos)
        return self.elements[i0-1 if i0 > 0 else 0]

    def el_pos(self, el):
        """Position for matching / output."""
        return el.position + el.length

    continuous_matching = False

    def adjust_match_pos(self, el, pos):
        if not self.continuous_matching:
            return self.el_pos(el)
        at, l = el.position, el.length
        if pos <= at:
            return at
        if pos >= at+l:
            return at+l
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
        new = _call(self.madx, self.path, name)
        if self.undo_stack:
            if new is None:
                # Have to clear the stack because general MAD-X commands are not
                # necessarily reversible (sequence definition, makethin, loading
                # tables, etc)!
                self.undo_stack.clear()
            else:
                text = "CALL {!r}".format(name)
                self._update(old, new, self._update_globals, text)
        self.invalidate()

    def load_strengths(self, filename):
        try:
            data = import_params(filename, data_key='globals')
        except ValueError as e:
            logging.error("Parser error in {!r}:\n{}".format(filename, e))
        else:
            self.update_globals(data)

    # Serialization

    # TODO: save reproducible state of workspace?
    def save(self, filename):
        """Save model to file."""
        yaml.save_file(filename, self.model_data())

    def model_data(self):
        """Return model data as dictionary."""
        return dict(self.data, **{
            'sequence': self.seq_name,
            'range': list(self.range),
            'beam': self.beam,
            'twiss': self.twiss_args,
        })

    def _init_segment(self, sequence, range, beam, twiss_args):
        """
        :param str sequence:
        :param tuple range:
        """

        self.sequence = self.madx.sequence[sequence]
        self.seq_name = self.sequence.name
        self.continuous_matching = True

        self._beam = beam = dict(beam, sequence=self.seq_name)
        self._twiss_args = twiss_args
        self.madx.command.beam(**beam)
        self.sequence.use()

        # Use `expanded_elements` rather than `elements` to have a one-to-one
        # correspondence with the data points of TWISS/SURVEY:
        self.elements = elems = ElementList(self.madx, self.seq_name)
        self.positions = self.sequence.expanded_element_positions()

        self.start, self.stop = self.parse_range(range)
        self.range = (normalize_range_name(self.start.name, elems),
                      normalize_range_name(self.stop.name, elems))

    def parse_range(self, range):
        """Convert a range str/tuple to a tuple of :class:`Element`."""
        if isinstance(range, str):
            range = range.split('/')
        start_name, stop_name = range
        return (self.elements[start_name],
                self.elements[stop_name])

    def export_globals(self, var_type=VAR_TYPE_DIRECT):
        return {
            k: p.value
            for k, p in self.globals.cmdpar.items()
            if p.inform and (p.var_type == var_type or var_type == any)
        }

    def export_beam(self):
        return dict(self.beam)

    def export_twiss(self):
        return dict(self.twiss_args)

    def fetch_beam(self):
        from madgui.widget.params import ParamInfo
        beam = self.beam
        pars = [
            ParamInfo(k.title(), v,
                      inform=k in beam,
                      mutable=k != 'sequence')
            for k, v in self.sequence.beam.items()
        ]
        ekin = (beam['energy'] - beam['mass']) / beam['mass']
        idx = next(i for i, p in enumerate(pars) if p.name.lower() == 'energy')
        pars.insert(idx, ParamInfo('E_kin', ekin))
        return pars

    def fetch_twiss(self):
        from madgui.widget.params import ParamInfo
        blacklist = ('sequence', 'line', 'range', 'notable')
        twiss_args = self.twiss_args
        return [
            ParamInfo(k.title(), twiss_args.get(k, v),
                      inform=k in twiss_args,
                      mutable=k not in blacklist)
            for k, v in self.madx.command.twiss.items()
        ]

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
        if self.undo_stack:
            self.undo_stack.push(action)
        else:
            action.redo()
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
        with self.madx.batch():
            for k, v in globals.items():
                if v is None:
                    v = 0
                elif v == '':
                    v = self.madx.globals[k]
                self.madx.globals[k] = v
        # TODO: invalidate only elements that depend updated variables?
        self.invalidate()

    def _update_beam(self, beam):
        new_beam = self.beam.copy()
        new_beam.update((k.lower(), v) for k, v in beam.items())
        if 'e_kin' in beam:
            eval = self.madx.eval
            ekin = eval(new_beam.get('e_kin'))
            mass = eval(new_beam.get('mass', 1))
            new_beam['energy'] = (ekin + 1) * mass
        new_beam.pop('e_kin', None)
        new_beam['sequence'] = self.seq_name
        self._beam = new_beam
        self.madx.command.beam(**new_beam)
        self.invalidate()

    def _update_twiss_args(self, twiss):
        new_twiss = self.twiss_args.copy()
        new_twiss.update((k.lower(), v) for k, v in twiss.items())
        self._twiss_args = new_twiss
        self.invalidate()

    def _update_element(self, data, elem_index):
        # TODO: this crashes for many parameters
        # - update only changed values
        elem = self.elements[elem_index]
        name = elem.node_name
        d = {k.lower(): v for k, v in data.items()
             if k in elem.cmdpar}
        if 'kick' in d and elem.base_name == 'sbend':
            # FIXME: This assumes the definition `k0:=(angle+k0)/l` and
            # will deliver incorrect results if this is not the case!
            var, = (set(self._get_knobs(elem, 'k0')) -
                    set(self._get_knobs(elem, 'angle')))
            self.madx.globals[var] = d.pop('kick')
        self.madx.elements[name](**d)

        self.invalidate()

    def get_twiss(self, elem, name, pos):
        """Return beam envelope at element."""
        ix = self.elements.index(elem)

        twiss = self.twiss()
        s = twiss.s
        y = twiss[name]
        x = self.indices[ix]

        # shortcut for thin elements:
        if float(self.elements[ix].length) == 0:
            return y[ix]

        lo = x.start-1 if x.start > 0 else x.start
        hi = x.stop+1

        i0 = bisect_right(s, pos, lo, hi)
        i1 = i0+1

        # never look outside the interpolation domain:
        if pos <= s[i0]:
            return y[i0]
        if pos >= s[i1]:
            return y[i1]

        dx = pos - s[i0]

        return y[i0] + dx * (y[i1]-y[i0]) / (s[i1]-s[i0])

    twiss_columns = [
        'alfx', 'alfy', 'betx', 'bety', 'gamx', 'gamy', 'ex', 'ey',
        'x', 'y', 'px', 'py', 'envx', 'envy',
    ]

    def get_elem_twiss(self, elem):
        tw = self.twiss()
        ix = self.elements.index(elem)
        i0 = self.indices[ix].stop
        return AttrDict({col: tw[col][i0] for col in self.twiss_columns})

    def get_elem_sigma(self, elem):
        ix = self.elements.index(elem)
        i0 = self.indices[ix].stop
        tw = self.twiss().row(i0, 'all')
        return [
            [tw['sig{}{}'.format(i+1, j+1)]
             for j in range(6)]
            for i in range(6)
        ]

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
        if elem_to is None:
            elem_to = elem_from
        if interval is None:
            interval = (0, 1)
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
        table = self.sector()
        maps = self.madx.sectortable(table._name)
        indices = [self.elements.index(el) for el in elems]
        x0, x1 = interval
        return [
            reduce(lambda a, b: np.dot(b, a),
                   maps[max(0, i+x0):max(0, j+x1)], np.eye(7))
            for i, j in zip(indices, indices[1:])
        ]

    # TODO: default values for knobs/monitors
    # TODO: pass entire optic (knob + delta)
    def get_orbit_response_matrix(
            self, monitors, knobs, errors=(), values=()) -> np.array:
        """
        Compute the orbit response matrix Δx/Δφ numerically (by varying knobs)
        and return as `M×2×K` matrix (monitors × x|y × knobs).
        """
        from .errors import apply_errors, Param
        madx = self.madx
        madx.command.select(flag='interpolate', clear=True)

        # applying errors here is a temporary measure until we figure out a
        # better way to take into account combined error effects (e.g.
        # relative error on top of absolute error):
        with apply_errors(self, errors, values):
            tw0 = madx.twiss(**self._get_twiss_args(table='orm_tmp'))
        x0, y0 = tw0.x, tw0.y
        idx = [self.elements.index(m) for m in monitors]

        def get_knob_response(var, step):
            """Return `2×M` matrix with responses for specified variable."""
            with apply_errors(self, [Param(var)], [step]):
                with apply_errors(self, errors, values):
                    tw1 = madx.twiss(**self._get_twiss_args(table='orm_tmp'))
            x1, y1 = tw1.x, tw1.y
            return np.vstack((
                (x1 - x0)[idx],
                (y1 - y0)[idx],
            )).T / step

        return np.dstack([
            get_knob_response(knob, 2e-4)
            for knob in knobs
        ])

    @memoize
    def survey(self):
        """Recalculate survey coordinates."""
        return self.madx.survey()

    def ex(self):
        return self.summary.ex

    def ey(self):
        return self.summary.ey

    @memoize
    def twiss(self, **kwargs):
        """Recalculate TWISS parameters."""
        self.madx.command.select(flag='interpolate', clear=True)
        if self.interpolate:
            step = self.sequence.elements[-1].position/self.interpolate
            self.madx.command.select(flag='interpolate', step=step)
        results = self.madx.twiss(**self._get_twiss_args(**kwargs))
        results = TwissTable(results._name, results._libmadx, _check=False)
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

    @memoize
    def sector(self):
        """Compute sectormaps of all elements."""
        # TODO: Ideally, we should compute sectormaps and twiss during the
        # same MAD-X TWISS command. But, since we don't need interpolated
        # sectormaps, this will require patching MAD-X first…
        self.madx.command.select(flag='interpolate', clear=True)
        # NOTE: we have to pass a different twiss table because madgui
        # currently fetches twiss columns only demand. Therefore, using the
        # same twiss table for both TWISS/SECTORMAP routines would lead to
        # inconsistent table lengths (interpolate vs no-interpolate!).
        self.madx.sectormap((), **self._get_twiss_args(
            table='sectortwiss', sectortable='sectortable'))
        return self.madx.table['sectortable']

    def track_one(self, x=0, px=0, y=0, py=0, range='#s/#e', **kwargs):
        """
        Track a particle through the sequence. Handles backward tracking (sort
        of) by specifying a negative range.

        Currently uses TWISS for tracking internally (to allow tracking
        through thick sequences). This might change.
        """
        elems = self.elements
        start, end = range.split('/') if isinstance(range, str) else range
        start, end = normalize_range_name(start), normalize_range_name(end)
        kwargs.setdefault('betx', 1)
        kwargs.setdefault('bety', 1)
        if elems.index(end) < elems.index(start):
            # TODO: we should use a separate madx process with inplace
            # reversed sequence for backtracking in the future, this will
            # simplify all the complications with element names etc.
            flip = {'#s': '#e', '#e': '#s'}
            start = flip.get(start, start + '_reversed')
            end = flip.get(end, end + '_reversed')
            tw = self.backtrack(
                x=-x, y=y, px=px, py=-py,
                range=start+'/'+end, **kwargs)
            return AttrDict({
                's': tw.s[-1] - tw.s,
                'x': -tw.x, 'px': tw.px,
                'y': tw.y, 'py': -tw.py,
            })
        return self.madx.twiss(
            x=x, px=px, y=y, py=py,
            range=range, **kwargs)

    backseq = None

    def backtrack(self, **twiss_init):
        """Backtrack final orbit through the reversed sequence."""
        if self.backseq is None:
            with self.madx.batch():
                self.backseq = self.seq_name + '_backseq'
                reverse_sequence(self.madx, self.backseq, self.elements)
        self.madx.command.select(flag='interpolate', clear=True)
        twiss_init.setdefault('betx', 1)
        twiss_init.setdefault('bety', 1)
        twiss_init.setdefault('table', 'backtrack')
        tw = self.madx.twiss(sequence=self.backseq, **twiss_init)
        tw = self.madx.table.backtrack
        self.invalidate()
        return tw

    def reverse(self):
        reverse_sequence_inplace(self.madx, self.seq_name)
        if self.undo_stack:
            self.undo_stack.clear()
        self._init_segment(
            sequence=self.seq_name,
            range='#s/#e',
            beam=self.beam,
            twiss_args={'betx': 1, 'bety': 1},
        )

    def match(self, vary, constraints, mirror_mode=True, **kwargs):

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
        # NOTE: Not sure we can measure or if there is a relevant
        # emittance dilution in the HEBT
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
                        method=('lmdif', {'calls': 2000, 'tolerance': 1e-8}),
                        **twiss_args)

        new_values = {v: self.read_param(v) for v in vary}

        if mirror_mode:
            fitResidual = self.madx.globals['TAR']
            isGoodFit = (fitResidual < 1e-6)
            if isGoodFit:
                self._update(old_values, new_values,
                             self._update_globals, "Match: {}")
            else:
                logging.warning('Fit Residual too high!!!')

        else:
            self._update(old_values, new_values,
                         self._update_globals, "Match: {}")

        # return corrections
        return new_values

    def read_monitor(self, name):
        """Mitigates read access to a monitor."""
        # TODO: handle split h-/v-monitor
        index = self.elements.index(name)
        twiss = self.twiss()
        return {
            'envx': twiss.envx[index],
            'envy': twiss.envy[index],
            'posx': twiss.x[index],
            'posy': twiss.y[index],
        }

    def _get_knobs(self, elem, attr):
        """Return list of all knob names belonging to the given attribute."""
        try:
            return _get_leaf_knobs(self.madx, elem.cmdpar[attr].expr)
        except IndexError:
            return []

    def read_param(self, expr):
        """Read element attribute. Return numeric value."""
        return self.madx.eval(expr)

    write_params = update_globals


class ElementList(ExpandedElementList):

    def __init__(self, madx, seq_name):
        super().__init__(madx, seq_name)
        self.names = madx._libmadx.get_expanded_element_names(seq_name)
        self._indices = {k: i for i, k in enumerate(self.names)}

    def __getitem__(self, key):
        index = self.index(key)
        elem = super().__getitem__(index)
        if elem.base_name == 'sbend':
            # MAD-X uses the condition k0=0 to check whether the attribute
            # should be used (even though that means you can never have a kick
            # that exactly counteracts the bending angle):
            elem._attr['kick'] = elem.k0 and elem.k0 * elem.length - elem.angle
        return elem

    def index(self, key):
        if isinstance(key, int):
            return key + len(self) if key < 0 else key
        elif isinstance(key, str):
            name = key.lower()
            if len(self) != 0:
                if name == '#s':
                    return 0
                elif name == '#e':
                    return len(self) - 1
            try:
                return self._indices[key.lower()]
            except KeyError as e:
                raise ValueError(key) from e
        elif hasattr(key, 'index'):
            return key.index
        raise TypeError(
            "Unknown key: {!r} ({})".format(key, type(key)))


# stuff for online control

def _get_leaf_knobs(madx, exprs):
    """
    Return knobs names for a given element attribute from MAD-X.

    >>> get_element_attribute(elements['r1qs1'], 'k1')
    ['kL_R1QS1']
    """
    cmdpar = madx.globals.cmdpar
    exprs = exprs if isinstance(exprs, list) else [exprs]
    exprs = [e for e in exprs if e]
    seen = set()
    vars = []
    while exprs:
        expr = exprs.pop(0)
        new = set(madx.expr_vars(expr)) - seen
        pars = [cmdpar[v] for v in new]
        vars.extend([p.name for p in pars if p.var_type == VAR_TYPE_DIRECT])
        exprs.extend([p.expr for p in pars if p.var_type == VAR_TYPE_DEFERRED])
        seen.update(new)
    return vars


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


def items(d):
    return d.items() if isinstance(d, Mapping) else d


def trim(s):
    return s.replace(' ', '') if isinstance(s, str) else s


_INVERT_ATTRS = {
    'sbend':        ['angle', 'k0'],
    'hkicker':      ['kick'],
    'kicker':       ['hkick'],
    'translation':  ['dy'],
}


def reverse_sequence(madx, name, elements):
    """
    Create a direction reversed copy of the sequence.

    :param Madx madx:
    :param str name: name of the reversed sequence
    :param list elements: list of elements
    """
    last = elements[-1]
    length = last.position + last.length

    madx.command.sequence.clone(name, l=length, refer='exit')
    for elem in reversed(elements):
        if elem.occ_cnt == 0 or '$' in elem.name:
            continue
        pos = elem.position
        overrides = {'at': length-pos}
        overrides.update({
            attr: "-{}->{}".format(elem.name, attr)
            for attr in _INVERT_ATTRS.get(elem.base_name, ())
        })
        if elem.base_name == 'sbend':
            overrides['e1'] = '-{}->e2'.format(elem.name)
            overrides['e2'] = '-{}->e1'.format(elem.name)

        elem.clone(elem.name + '_reversed', **overrides)

    madx.command.endsequence()

    madx.command.beam(sequence=name)
    madx.use(name)


def reverse_sequence_inplace(madx, seq_name):
    cmd = madx.command
    cmd.seqedit(sequence=seq_name)
    cmd.flatten()
    cmd.reflect()
    cmd.endedit()

    for elem in reversed(madx.sequence[seq_name].elements):
        if elem.occ_cnt == 0 or '$' in elem.name:
            continue
        overrides = {}
        overrides.update({
            attr: negate_expr(elem.defs[attr])
            for attr in _INVERT_ATTRS.get(elem.base_name, ())
        })
        if elem.base_name == 'sbend':
            overrides['e1'] = negate_expr(elem.defs.e2)
            overrides['e2'] = negate_expr(elem.defs.e1)

        if overrides:
            elem(**overrides)


def negate_expr(value):
    return "-({})".format(value) if isinstance(value, str) else -value


class TwissTable(Table):

    """
    Provide the following features on top of :class:`cpymad.madx.Table`:

    - add columns for one-sigma beam envelopes: envx, envy
    - add columns for gamma optical function: gamx, gamy
    - add aliases for beam position: posx, posy
    - override twiss alfa/beta parameters and emittances from the sigma matrix,
      i.e. in the local reference rather than normal coordinates.
    """

    _transform = {
        'alfx': lambda self: -self.sig12 / self.ex,
        'alfy': lambda self: -self.sig34 / self.ey,
        'betx': lambda self: +self.sig11 / self.ex,
        'bety': lambda self: +self.sig33 / self.ey,
        'gamx': lambda self: +self.sig22 / self.ex,
        'gamy': lambda self: +self.sig44 / self.ey,
        'envx': lambda self: self.sig11**0.5,
        'envy': lambda self: self.sig33**0.5,
        'posx': lambda self: self.x,
        'posy': lambda self: self.y,
        'ex': lambda self: (self.sig11 * self.sig22 -
                            self.sig12 * self.sig21)**0.5,
        'ey': lambda self: (self.sig33 * self.sig44 -
                            self.sig34 * self.sig43)**0.5,
    }

    def _query(self, column):
        """Retrieve the column data."""
        transform = self._transform.get(column)
        if transform is None:
            return super()._query(column)
        else:
            return transform(self)


def _load_params(data, name, path):
    """Load parameter dict from file if necessary."""
    vals = data.get(name, {})
    if isinstance(vals, str):
        data[name] = yaml.load_file(os.path.join(path, vals))
        if len(data[name]) == 1 and name in data[name]:
            data[name] = data[name][name]


def _call(madx, path, name):
    """Load a MAD-X file into the current workspace."""
    name = os.path.join(path, name)
    vals = read_str_file(name)
    madx.call(name, True)
    return vals


def _guess_main_sequence(madx):
    """Try to guess the 'main' sequence to be viewed."""
    sequence = madx.sequence()
    if sequence:
        return sequence.name
    sequences = madx.sequence
    if not sequences:
        raise ValueError("No sequences defined!")
    if len(sequences) != 1:
        # TODO: ask user which one to use
        raise ValueError("Multiple sequences defined, none active. "
                         "Cannot uniquely determine which to use.")
    return next(iter(sequences))


def _get_seq_model(madx, sequence_name):
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
        sequence = madx.sequence[sequence_name]
    except KeyError:
        raise RuntimeError("The sequence is not defined.")
    try:
        beam = sequence.beam
    except RuntimeError:
        beam = {}
    try:
        range, twiss = _get_twiss(madx, sequence)
    except RuntimeError:
        range = (sequence_name+'$start', sequence_name+'$end')
        twiss = {}
    return {
        'sequence': sequence_name,
        'range': range,
        'beam': _eval_expr(beam),
        'twiss': _eval_expr(twiss),
    }


def _get_twiss(madx, sequence):
    """
    Try to determine (range, twiss) from the MAD-X state.

    :raises RuntimeError: if unable to make a useful guess
    """
    table = sequence.twiss_table        # raises RuntimeError
    try:
        first, last = table.range
    except ValueError:
        raise RuntimeError("TWISS table inaccessible or nonsensical.")
    if first not in sequence.expanded_elements or \
            last not in sequence.expanded_elements:
        raise RuntimeError(
            "The TWISS table appears to belong to a different sequence.")
    mandatory = {'betx', 'bety', 'alfx', 'alfy'}
    defaults = madx.command.twiss
    # TODO: periodic lines -> only mux/muy/deltap
    # TODO: logical parameters like CHROM
    twiss = {
        key: float(val)
        for key, val in table[0].items()
        if isinstance(val, Number) and (
                (key in mandatory) or
                (key in defaults and val != defaults.cmdpar[key].value)
        )
    }
    return (first, last), twiss
