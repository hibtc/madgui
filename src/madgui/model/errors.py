"""
This module defines functions and classes to load and represent MAD-X model
errors, such as alignment errors or field errors.

Errors are represented as strings such as::

    'Δax_b3mu1'         # absolute error in parameter
    'δax_b3mu1'         # relative error in parameter
    'Δb3mu1v->kick'     # absolute error in element attribute
    'g3mu1<dx>'         # alignment error
"""

__all__ = [
    'import_errors',
    'apply_errors',
    'parse_error',
    'Param',
    'Ealign',
    'Efcomp',
    'ElemAttr',
    'InitTwiss',
    'ScaleAttr',
    'ScaleParam',
    'BaseError',
    'RelativeError',
]

import re
from contextlib import ExitStack

from cpymad.util import is_identifier


def import_errors(model, spec: dict):
    """
    Apply errors to a model defined by a dictionary ``{error: value}`` with
    types ``{str: float}``. The error keys are parsed by ``parse_error``.
    """
    return apply_errors(
        model, map(parse_error, spec.keys()), spec.values())


def apply_errors(model, errors, values):
    """Apply list of errors and list of corresponding values to a given model."""
    with ExitStack() as stack:
        for error, value in zip(errors, values):
            stack.enter_context(error.vary(model, value))
        return stack.pop_all()


def parse_error(name):
    """
    Instanciate a subtype of :class:`BaseError`, depending on the format of
    ``name``. We currently understand the following formats::

        x               -> InitTwiss
        Δax_b3mu1       -> ElemAttr
        δax_b3mu1       -> ScaleAttr
        Δg3mu1->angle   -> Param
        δg3mu1->angle   -> ScaleParam
        g3mu1<dx>       -> Ealign
    """

    mult = name.startswith('δ')
    name = name.lstrip('δΔ \t')
    if name in ('x', 'y', 'px', 'py'):
        return InitTwiss(name)
    if '->' in name:
        elem, attr = name.split('->')
        if mult:
            return ScaleAttr(elem, attr)
        return ElemAttr(elem, attr)
    if '<' in name:
        elem, attr = re.match(r'(.*)\<(.*)\>', name).groups()
        return Ealign({'range': elem}, attr)
    if is_identifier(name):
        if mult:
            return ScaleParam(name)
        return Param(name)
    # TODO: efcomp field errors!
    raise ValueError("{!r} is not a valid error specification!".format(name))


class BaseError:

    """
    Base class for model errors.

    Subclasses must implement ``get``, ``set``, and ``tinker``.

    In the simplest case, ``get`` returns the current value of the error,
    ``tinker`` returns the given step, and ``set`` sets a variable. However,
    this logic is not always available. In general, the following protocol
    must be implemented:

    - :meth:`get`: return a backup value that will be later used to restore
      the current error value
    - :meth:`tinker` returns a value that should be used to update the current
      value
    - :meth:`set` is called with the return value of :meth:`tinker` to change
      the value of the error, and later with the return value of :meth:`get`
      to restore to the original state.
    """

    leader = 'Δ'

    def __init__(self, name):
        self.name = name

    def vary(self, model, step):
        """Applies the error and returns a context manager that restores the
        error to its original value on exit."""
        old = self.get(model, step)
        new = self.tinker(old, step)
        with ExitStack() as stack:
            if new != old:
                self.set(model, new)
                stack.callback(self.set, model, old)
            return stack.pop_all()

    def get(self, model, step):
        """Get a "backup" value that represents with what :meth:`set` should
        be called to restore the current value."""
        return 0.0

    def set(self, model, value):
        """Update the error value."""
        raise NotImplementedError

    def __repr__(self):
        return "{}{}".format(self.leader, self.name)

    def tinker(self, value, step):
        """Return the value that should be passed to :meth:`set` in order to
        increment the error by ``step``. ``value`` is provided as the return
        value of :meth:`get`."""
        if isinstance(value, str):
            return "({}) + ({})".format(value, step)
        elif value is None:
            return step
        else:
            return value + step


class Param(BaseError):

    """Error on a global variable (knob)."""

    def get(self, model, step):
        return model.globals.cmdpar[self.name].definition

    def set(self, model, value):
        model.globals[self.name] = value


class Ealign(BaseError):

    """Alignment error."""

    def __init__(self, select, attr):
        self.select = select
        self.attr = attr
        self.name = '{}<{}>'.format(select.get('range'), attr)

    def set(self, model, value):
        cmd = model.madx.command
        cmd.select(flag='error', clear=True)
        cmd.select(flag='error', **self.select)
        cmd.ealign(**{self.attr: value})

    def get(self, model, step):
        return -step

    def tinker(self, value, step):
        return -value


class Efcomp(BaseError):

    """Field error."""

    def __init__(self, select, attr, value, order=0, radius=1):
        self.select = select
        self.attr = attr
        self.value = value
        self.order = order
        self.radius = radius
        self.name = '{}+{}'.format(select['range'], attr)

    def set(self, model, value):
        cmd = model.madx.command
        cmd.select(flag='error', clear=True)
        cmd.select(flag='error', **self.select)
        cmd.efcomp(**{
            'order': self.order,
            'radius': self.radius,
            self.attr: [v * value for v in self.value],
        })

    def get(self, model, step):
        return -step

    def tinker(self, value, step):
        return -value


class ElemAttr(BaseError):

    """Element attribute error."""

    def __init__(self, elem, attr):
        self.elem = elem
        self.attr = attr
        self.name = '{}->{}'.format(elem, attr)

    def get(self, model, step):
        return model.elements[self.elem].cmdpar[self.attr].definition

    def set(self, model, value):
        model.elements[self.elem][self.attr] = value


class InitTwiss(BaseError):

    """Error in twiss initial condition (x, px, y, py)."""

    def get(self, model, step):
        return model.twiss_args.get(self.name)

    def set(self, model, value):
        model.update_twiss_args({self.name: value})


class RelativeError(BaseError):

    """Base class for relative errors."""

    leader = 'δ'

    def tinker(self, value, step):
        if isinstance(value, str):
            return "({}) * ({})".format(value, 1 + step)
        elif value is None:
            return None
        else:
            return value * (1 + step)


class ScaleAttr(RelativeError, ElemAttr):
    """Relative element attribute error."""


class ScaleParam(RelativeError, Param):
    """Relative global variable error."""
