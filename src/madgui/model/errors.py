import re
from contextlib import contextmanager, ExitStack

from cpymad.util import is_identifier


def apply_errors(model, errors, values):
    with ExitStack() as stack:
        for error, value in zip(errors, values):
            stack.enter_context(error.vary(model, value))
        return stack.pop_all()


def parse_error(name):
    mult = name.endswith('*')
    name = name.rstrip('*')
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

    @contextmanager
    def vary(self, model, step):
        memo = self.apply(model, step)
        try:
            yield step
        finally:
            self.restore(model, -step if memo is None else memo)

    def restore(self, model, value):
        self.apply(model, value)

    def __repr__(self):
        return "{}{}".format(self.leader, self.name)


class Param(BaseError):

    """Variable parameter."""

    def __init__(self, name):
        self.name = name

    def apply(self, model, value):
        memo = model.globals.cmdpar[self.name].definition
        model.globals[self.name] += value
        return memo

    def restore(self, model, value):
        model.globals[self.name] = value


class Ealign(BaseError):

    """Alignment error."""

    def __init__(self, select, attr):
        self.select = select
        self.attr = attr
        self.name = '{}<{}>'.format(select.get('range'), attr)

    def apply(self, model, value):
        cmd = model.madx.command
        cmd.select(flag='error', clear=True)
        cmd.select(flag='error', **self.select)
        cmd.ealign(**{self.attr: value})


class Efcomp(BaseError):

    """Field error."""

    def __init__(self, select, attr, value, order=0, radius=1):
        self.select = select
        self.attr = attr
        self.value = value
        self.order = order
        self.radius = radius
        self.name = '{}+{}'.format(select['range'], attr)

    def apply(self, model, value):
        cmd = model.madx.command
        cmd.select(flag='error', clear=True)
        cmd.select(flag='error', **self.select)
        cmd.efcomp(**{
            'order': self.order,
            'radius': self.radius,
            self.attr: [v * value for v in self.value],
        })


class ElemAttr(BaseError):

    """Variable parameter."""

    def __init__(self, elem, attr):
        self.elem = elem
        self.attr = attr
        self.name = '{}->{}'.format(elem, attr)

    def apply(self, model, value):
        elem = model.elements[self.elem]
        memo = elem.cmdpar[self.attr].definition
        elem[self.attr] = "({}) + ({})".format(memo, value)
        return memo

    def restore(self, model, value):
        model.elements[self.elem][self.attr] = value


class InitTwiss(BaseError):

    def __init__(self, name):
        self.name = name

    def apply(self, model, value):
        memo = model.twiss_args.get(self.name)
        model.update_twiss_args({self.name: (memo or 0.0) + value})
        return memo

    def restore(self, model, value):
        model.update_twiss_args({self.name: value})


class ScaleAttr(ElemAttr):

    leader = 'δ'

    def apply(self, model, value):
        elem = model.elements[self.elem]
        memo = elem.cmdpar[self.attr].definition
        elem[self.attr] = "({}) * ({})".format(memo, 1+value)
        return memo

    def restore(self, model, value):
        model.elements[self.elem][self.attr] = value


class ScaleParam(Param):

    leader = 'δ'

    def apply(self, model, value):
        memo = model.globals.cmdpar[self.name].definition
        model.globals[self.name] *= 1+value
        return memo

    def restore(self, model, value):
        model.globals[self.name] = value
