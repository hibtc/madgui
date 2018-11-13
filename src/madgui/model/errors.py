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
        old = self.get(model)
        new = self.tinker(old, step)
        self.set(model, new)
        try:
            yield step
        finally:
            self.set(model, old)

    def get(self, model):
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

    def __init__(self, name):
        self.name = name

    def get(self, model):
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


class ElemAttr(BaseError):

    """Variable parameter."""

    def __init__(self, elem, attr):
        self.elem = elem
        self.attr = attr
        self.name = '{}->{}'.format(elem, attr)

    def get(self, model):
        return model.elements[self.elem].cmdpar[self.attr].definition

    def set(self, model, value):
        model.elements[self.elem][self.attr] = value


class InitTwiss(BaseError):

    def __init__(self, name):
        self.name = name

    def get(self, model):
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
