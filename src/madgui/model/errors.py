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

    """Variable parameter."""

    def __init__(self, elem, attr):
        self.elem = elem
        self.attr = attr
        self.name = '{}->{}'.format(elem, attr)

    def get(self, model, step):
        return model.elements[self.elem].cmdpar[self.attr].definition

    def set(self, model, value):
        model.elements[self.elem][self.attr] = value


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
    pass


class ScaleParam(RelativeError, Param):
    pass
