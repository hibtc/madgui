"""
Shared base classes for different backends.
"""

from abc import abstractmethod
from bisect import bisect_right
from collections import namedtuple, Sequence, Mapping
import re

import numpy as np

from madqt.core.base import Object, Signal, Cache
from madqt.core.unit import from_config
from madqt.resource.package import PackageResource
from madqt.util.misc import cachedproperty


__all__ = [
    'ElementInfo',
    'FloorCoords',
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


class BaseModel(Object):

    """

    Abstract properties:

        backend             backend object
        backend_libname     name of the binding.
        backend_title       ui title of the backend accelerator code.
    """

    destroyed = Signal()
    matcher = None

    def __init__(self, filename, app_config):
        super().__init__()
        self.twiss = Cache(self._retrack)
        self.app_config = app_config
        module = self.__class__.__module__.rsplit('.', 1)[-1]
        self.config = PackageResource('madqt.engine').yaml(module + '.yml')
        self.load(filename)
        self.twiss.invalidate()

    def minrpc_flags(self):
        """Flags for launching the backend library in a remote process."""
        import subprocess
        from threading import RLock
        return dict(lock=RLock(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def destroy(self):
        """Annihilate current model. Stop interpreter."""
        if self.rpc_client:
            self.rpc_client.close()
        self.backend = None
        self.destroyed.emit()

    @property
    def rpc_client(self):
        """Low level RPC client."""
        return self.backend and self.backend._service

    @property
    def remote_process(self):
        """Backend process."""
        return self.backend and self.backend._process

    def _load_params(self, data, name):
        """Load parameter dict from file if necessary."""
        vals = data.get(name, {})
        if isinstance(vals, str):
            data[name] = self.repo.yaml(vals, encoding='utf-8')
            if len(data[name]) == 1 and name in data[name]:
                data[name] = data[name][name]

    def elements(self):
        raise NotImplementedError

    def survey(self):
        raise NotImplementedError

    def get_twiss_args_raw(self, elem):
        raise NotImplementedError

    def get_element_index(self, elem):
        raise NotImplementedError

    def data(self):
        return {
            'sequence': self.sequence,
            'range': self.range,
            'beam': self.beam,
            'twiss': self.twiss_args,
        }

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

    beam = property(get_beam, set_beam)
    twiss_args = property(get_twiss_args, set_twiss_args)

    def get_element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        if pos is None:
            return None
        val = self.utool.strip_unit('s', pos)
        i0 = bisect_right(self.positions, val)
        if i0 == 0:
            return None
        elem = self.elements[i0-1]
        at, L = elem['at'], elem['l']
        if pos < at or pos > at+L:
            return None
        return elem

    def get_element_by_name(self, name):
        return self.elements[self.get_element_index(name)]

    def el_pos(self, el):
        """Position for matching / output."""
        return el['at'] + el['l']

    continuous_matching = False

    def adjust_match_pos(self, el, pos):
        if not self.continuous_matching:
            return self.el_pos(el)
        at, l = el['at'], el['l']
        if pos <= at:   return at
        if pos >= at+l: return at+l
        return pos

    def get_best_match_pos(self, pos):
        """Find optics element by longitudinal position."""
        elem = min(filter(self.can_match_at, self.elements),
                   key=lambda el: abs(self.adjust_match_pos(el, pos)-pos))
        return min([
            (el, self.adjust_match_pos(el, pos))
            for el in self.elements
            if self.can_match_at(el)
        ], key=lambda x: abs(x[1]-pos))

    def can_match_at(self, element):
        return True

    def set_element_attribute(self, elem, attr, value):
        elem = self.elements[elem]['el_id']
        self.get_elem_ds(elem).substores['attributes'].update({
            attr: value,
        })
    # curves

    @property
    def curve_style(self):
        return self.config['curve_style']

    @cachedproperty
    def builtin_graphs(self):
        return {
            info['name']: PlotInfo(
                name=info['name'],
                title=info['title'],
                curves=[
                    CurveInfo(
                        name=curve['name'],
                        short=curve['short'],
                        label=curve['label'],
                        style=self.curve_style[curve_index],
                        unit=from_config(curve['unit']))
                    for curve_index, curve in enumerate(info['curves'])
                ])
            for info in self.app_config['builtin_graphs']
        }

    @cachedproperty
    def native_graphs(self):
        return self.get_native_graphs()

    def get_graph_data(self, name, xlim):
        """
        Get the data for a particular graph as dict of numpy arrays.

        :rtype: PlotInfo
        """
        if xlim is not None:
            xlim = tuple(self.utool.strip_unit('s', lim)
                         for lim in self.elements.bound_range(xlim))
        if name in self.native_graphs:
            return self.get_native_graph_data(name, xlim)
        info = self.builtin_graphs[name]
        if name == 'envelope':
            emittances = self.ex(), self.ey()
            # beta = env^2 / emit
            # env = sqrt(beta * emit)
            beta, data = self.get_native_graph_data('beta', xlim)
            data = {
                env_i.name: np.hstack((
                    data[beta_i.name][:,[0]],
                    (data[beta_i.name][:,[1]] * emit)**0.5
                ))
                for beta_i, env_i, emit in zip(
                        beta.curves, info.curves, emittances)
            }
        else:
            raise ValueError("Unknown graph: {}".format(name))
        return info, data

    def get_graphs(self):
        graphs = {
            name: info.title
            for name, info in self.builtin_graphs.items()
        }
        graphs.update(self.native_graphs)
        return graphs

    @abstractmethod
    def get_native_graph_data(self, name, xlim):
        """Get the data for a particular graph."""
        raise NotImplementedError

    @abstractmethod
    def get_native_graphs(self):
        """Get a list of graph names."""
        raise NotImplementedError

    @abstractmethod
    def _retrack(self):
        raise NotImplementedError

    @abstractmethod
    def match(self, variables, constraints):
        raise NotImplementedError

    def get_matcher(self):
        if self.matcher is None:
            # TODO: create MatchDialog
            from madqt.correct.match import Matcher
            self.matcher = Matcher(self, self.app_config['matching'])
        return self.matcher

    @abstractmethod
    def get_knob(self, element, attr):
        """Return a :class:`Knob` belonging to the given attribute."""

    @abstractmethod
    def read_param(self, param):
        """Read element attribute. Return numeric value. No units!"""

    @abstractmethod
    def write_param(self, param, value):
        """Update element attribute into control system. No units!"""


class ElementBase(Mapping):

    """
    Dict-like base class for elements. Provides attribute access to properties
    by title case attribute names.

    Subclasses must implement ``_retrieve`` and ``invalidate``.
    """

    # Do not rely on the numeric values, they may be replaced by flags!
    INVALIDATE_TWISS = 0
    INVALIDATE_PARAM = 1
    INVALIDATE_ALL   = 2

    def __init__(self, engine, utool, idx, name):
        self._engine = engine
        self._utool = utool
        self._idx = idx
        self._name = name.lower()
        self.invalidate(self.INVALIDATE_ALL)

    @abstractmethod
    def invalidate(self, level=INVALIDATE_ALL):
        """Invalidate cached data at and below the given level."""

    @abstractmethod
    def _retrieve(self, name):
        """Retrieve data for key if possible; everything if None."""

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
            self.min_x = beg['at']
            self.max_x = end['at'] + end['l']
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
        if isinstance(index, (dict, ElementBase)):
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
        if isinstance(element, (dict, ElementBase)):
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
        index = elem['el_id']
        data = self._get_by_index(index)
        if elem['name'] != data['name']:
            raise ValueError("Element name mismatch: expected {}, got {}."
                             .format(data['name'], elem['name']))
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
        index = elem['el_id']
        if elem['name'].lower() != self._el_names[index].lower():
            raise ValueError("Element name mismatch: expected {}, got {}."
                             .format(self._el_names[index], elem['name']))
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
