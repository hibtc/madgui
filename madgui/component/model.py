# encoding: utf-8
"""
Model component for the MadGUI application.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core.plugin import HookCollection

# exported symbols
__all__ = ['Model']


class Model(object):

    """
    Extended model class for cpymad.model (extends by delegation).

    :ivar Madx madx:
    :ivar list elements:
    :ivar dict twiss_args:
    """

    # TODO: separate into multipble components:
    #
    # - MadX
    # - metadata (cpymad.model?)
    # - Sequence (elements)
    # - Matcher
    #
    # The MadX instance should be connected to a specific frame at
    # construction time and log all output there in two separate places
    # (panels?):
    #   - logging.XXX
    #   - MAD-X library output
    #
    # Some properties (like `elements` in particular) can not be determined
    # at construction time and must be retrieved later on. Generally,
    # `elements` can come from two sources:
    # - MAD-X memory
    # - metadata
    # A reasonable mechanism is needed to resolve/update it.

    # TODO: more logging
    # TODO: automatically switch directories when CALLing files

    def __init__(self,
                 madx,
                 utool,
                 name=None,
                 twiss_args=None,
                 elements=None,
                 model=None):
        """
        """
        self.hook = HookCollection(
            show='madgui.component.model.show',
            update=None)

        self.madx = madx
        self.utool = utool
        self.name = name
        self.twiss_args = twiss_args
        self._columns = ['name', 'l', 'angle', 'k1l',
                         's',
                         'x', 'y',
                         'betx','bety']
        self._update_elements(elements)
        self.model = model
        try:
            seq = madx.get_active_sequence()
            tw = seq.twiss
        except (RuntimeError, ValueError):
            # TODO: init members
            pass
        else:
            self._update_twiss(tw)

    @property
    def can_match(self):
        return bool(self.twiss_args)

    @property
    def can_select(self):
        return bool(self.elements)

    @property
    def beam(self):
        """Get the beam parameter dictionary."""
        beam = self.madx.get_sequence(self.name).beam
        return self.utool.dict_add_unit(beam)

    @beam.setter
    def beam(self):
        """Set beam from a parameter dictionary."""

    def element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        if pos is None:
            return None
        for elem in self.elements:
            at, L = elem['at'], elem['l']
            if pos >= at and pos <= at+L:
                return elem
        return None

    def element_by_name(self, name):
        """Find the element in the sequence list by its name."""
        for elem in self.elements:
            if elem['name'].lower() == name.lower():
                return elem
        return None

    def element_by_position_center(self, pos):
        """Find next element by longitudinal center position."""
        if pos is None:
            return None
        found_at = None
        found_elem = None
        for elem in self.elements:
            at, L = elem['at'], elem['l']
            center = at + L/2
            if found_elem is None or abs(pos - at) < abs(pos - found_at):
                found_at = at
                found_elem = elem
        return found_elem

    def twiss(self):
        """Recalculate TWISS parameters."""
        twiss_args = self.utool.dict_strip_unit(self.twiss_args)
        results = self.madx.twiss(sequence=self.name,
                                  columns=self._columns,
                                  twiss_init=twiss_args)
        self._update_twiss(results)

    def _update_twiss(self, results):
        """Update TWISS results."""
        data = results.copy()
        self.tw = self.utool.dict_add_unit(data)
        self.summary = self.utool.dict_add_unit(results.summary)
        self.update()

    def _update_elements(self, elements=None):
        if elements is None:
            try:
                sequence = self.madx.get_active_sequence()
                elements = sequence.get_elements()
            except RuntimeError:
                self.elements = []
                return
        self.elements = list(map(self.utool.dict_add_unit, elements))

    def element_index_by_name(self, name):
        """Find the element index in the twiss array by its name."""
        ln = name.lower()
        return next(i for i,v in enumerate(self.tw['name']) if v.lower() == ln)

    def get_element_index(self, elem):
        """Get element index by it name."""
        return self.element_index_by_name(elem['name'])

    def get_twiss(self, elem, name):
        """Return beam envelope at element."""
        return self.tw[name][self.get_element_index(elem)]

    def get_twiss_center(self, elem, name):
        """Return beam envelope at center of element."""
        i = self.get_element_index(elem)
        prev = i - 1 if i != 0 else i
        return (self.tw[name][i] + self.tw[name][prev]) / 2

    def update(self):
        """Perform post processing."""
        # data post processing
        self.pos = self.tw['s']
        self.tw['envx'] = (self.tw['betx'] * self.summary['ex'])**0.5
        self.tw['envy'] = (self.tw['bety'] * self.summary['ey'])**0.5
        # Create aliases for x,y that have non-empty common prefix. The goal
        # is to make the config file entries less awkward that hold this
        # prefix:
        self.tw['posx'] = self.tw['x']
        self.tw['posy'] = self.tw['y']
        self.hook.update()

    def evaluate(self, expr):
        """Evaluate a MADX expression and return the result as float."""
        return self.madx.evaluate(expr)

