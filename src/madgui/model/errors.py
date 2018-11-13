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
        madx = model.madx
        self.apply(madx, step)
        try:
            yield step
        finally:
            self.apply(madx, -step)

    def __repr__(self):
        return "{}{}".format(self.leader, self.name)


class Param(BaseError):

    """Variable parameter."""

    def __init__(self, name):
        self.name = name

    def apply(self, madx, value):
        madx.globals[self.name] += value


class Ealign(BaseError):

    """Alignment error."""

    def __init__(self, select, attr):
        self.select = select
        self.attr = attr
        self.name = '{}<{}>'.format(select.get('range'), attr)

    def apply(self, madx, value):
        cmd = madx.command
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

    def apply(self, madx, value):
        cmd = madx.command
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

    @contextmanager
    def vary(self, model, step):
        madx = model.madx
        backup = madx.elements[self.elem].cmdpar[self.attr].definition
        self.apply(madx, step)
        try:
            yield step
        finally:
            madx.elements[self.elem][self.attr] = backup

    def apply(self, madx, value):
        madx.elements[self.elem][self.attr] = "({}) + ({})".format(
            madx.elements[self.elem].cmdpar[self.attr].definition, value)


class InitTwiss(BaseError):

    def __init__(self, name):
        self.name = name

    @contextmanager
    def vary(self, model, step):
        self.apply(model, step)
        try:
            yield step
        finally:
            self.apply(model, -step)

    def apply(self, model, value):
        model.update_twiss_args({
            self.name: model.twiss_args.get(self.name, 0.0) + value
        })


class ScaleAttr(ElemAttr):

    leader = 'δ'

    def apply(self, madx, value):
        madx.elements[self.elem][self.attr] = "({}) * ({})".format(
            madx.elements[self.elem].cmdpar[self.attr].definition, 1+value)


class ScaleParam(Param):

    leader = 'δ'

    @contextmanager
    def vary(self, model, step):
        madx = model.madx
        backup = madx.globals.cmdpar[self.name].definition
        self.apply(madx, step)
        try:
            yield step
        finally:
            madx.globals[self.name] = backup

    def apply(self, madx, value):
        madx.globals[self.name] *= 1+value
