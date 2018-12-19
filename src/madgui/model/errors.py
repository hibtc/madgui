import re
from contextlib import ExitStack

from cpymad.util import is_identifier


def import_errors(model, spec):
    return apply_errors(
        model, map(parse_error, spec.keys()), spec.values())


def apply_errors(model, errors, values):
    with ExitStack() as stack:
        for error, value in zip(errors, values):
            stack.enter_context(error.vary(model, value))
        return stack.pop_all()


def apply_reverse_errors(model, errors, values):
    return apply_errors(model, *zip(*[
        reverse_error(model, err, val)
        for err, val in zip(errors, values)
    ]))


def reverse_error(model, error, value):
    return error.reversed(model, value)


def parse_error(name):
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

    leader = 'Δ'

    def __init__(self, name):
        self.name = name

    def vary(self, model, step):
        old = self.get(model, step)
        new = self.tinker(old, step)
        with ExitStack() as stack:
            if new != old:
                self.set(model, new)
                stack.callback(self.set, model, old)
            return stack.pop_all()

    def get(self, model, step):
        return 0.0

    def set(self, model, value):
        raise NotImplementedError

    def __repr__(self):
        return "{}{}".format(self.leader, self.name)

    def tinker(self, value, step):
        if isinstance(value, str):
            return "({}) + ({})".format(value, step)
        elif value is None:
            return step
        else:
            return value + step

    def reversed(self, model, value):
        return self, value


class Param(BaseError):

    """Variable parameter."""

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

    def reversed(self, model, value):
        negate = self.attr in ('dx', 'ds')
        return self, value * (-1 if negate else +1)


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

    def reversed(self, model, value):
        # TODO: …
        return self, value


class ElemAttr(BaseError):

    """Variable parameter."""

    def __init__(self, elem, attr):
        self.elem = elem
        self.attr = attr
        self.name = '{}->{}'.format(elem, attr)

    def get(self, model, step):
        return model.elements[self.elem].cmdpar[self.attr].definition

    def set(self, model, value):
        model.elements[self.elem][self.attr] = value

    def reversed(self, model, value):
        rev_elem = self.elem + '_reversed'
        rev_attr = _EXCHANGE.get(self.attr, self.attr)
        elem = model.elements[self.elem]
        negate = self.attr in _NEGATE.get(elem.base_name, ())
        return ElemAttr(rev_elem, rev_attr), value * (-1 if negate else +1)


_EXCHANGE = {'e1': 'e2', 'e2': 'e1'}
_NEGATE =  {
    'sbend':        ['angle', 'k0', 'e1', 'e2'],
    'hkicker':      ['kick'],
    'kicker':       ['hkick'],
    'translation':  ['px', 'y'],
}


class InitTwiss(BaseError):

    def get(self, model, step):
        return model.twiss_args.get(self.name)

    def set(self, model, value):
        model.update_twiss_args({self.name: value})


class RelativeError(BaseError):

    leader = 'δ'

    def tinker(self, value, step):
        if isinstance(value, str):
            return "({}) * ({})".format(value, 1 + step)
        elif value is None:
            return None
        else:
            return value * (1 + step)


class ScaleAttr(RelativeError, ElemAttr):

    def reversed(self, model, value):
        # don't negate value
        rev_elem = self.elem + '_reversed'
        rev_attr = _EXCHANGE.get(self.attr, self.attr)
        return ElemAttr(rev_elem, rev_attr), value


class ScaleParam(RelativeError, Param):
    pass
