from contextlib import contextmanager, ExitStack


def apply_errors(model, errors, values):
    with ExitStack() as stack:
        for error, value in zip(errors, values):
            error.step = value
            stack.enter_context(error.vary(model))
        return stack.pop_all()


class BaseError:

    leader = 'Δ'

    def __init__(self, step):
        self.base = 0.0
        self.step = step

    def set_base(self, madx):
        self.base = 0.0

    @contextmanager
    def vary(self, model):
        madx = model.madx
        step = self.step
        self.apply(madx, step)
        try:
            yield step
        finally:
            self.apply(madx, -step)

    def __repr__(self):
        return "[{}{}={}]".format(self.leader, self.name, self.step)


class Param(BaseError):

    """Variable parameter."""

    def __init__(self, knob, step=1e-4, madx=None):
        super().__init__(step)
        self.knob = self.name = knob
        if madx is not None:
            self.set_base(madx)

    def set_base(self, madx):
        self.base = madx.globals[self.knob]

    def apply(self, madx, value):
        madx.globals[self.knob] += value


class Ealign(BaseError):

    """Alignment error."""

    def __init__(self, select, attr, step):
        super().__init__(step)
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
        super().__init__(sum(value))
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

    def __init__(self, elem, attr, step=1e-4, madx=None):
        super().__init__(step)
        self.elem = elem
        self.attr = attr
        if madx is not None:
            self.set_base(madx)
        self.name = '{}->{}'.format(elem, attr)

    def set_base(self, madx):
        self.base = madx.elements[self.elem][self.attr]

    @contextmanager
    def vary(self, model):
        madx = model.madx
        step = self.step
        backup = madx.elements[self.elem].cmdpar[self.attr].definition
        self.apply(madx, step)
        try:
            yield step
        finally:
            madx.elements[self.elem][self.attr] = backup

    def apply(self, madx, value):
        madx.elements[self.elem][self.attr] = "({}) + ({})".format(
            madx.elements[self.elem].cmdpar[self.attr].definition, value)


class ScaleAttr(ElemAttr):

    leader = 'δ'

    def set_base(self, madx):
        self.base = 0.0

    def apply(self, madx, value):
        madx.elements[self.elem][self.attr] = "({}) * ({})".format(
            madx.elements[self.elem].cmdpar[self.attr].definition, 1+value)


class ScaleParam(Param):

    leader = 'δ'

    def set_base(self, madx):
        self.base = 0.0

    @contextmanager
    def vary(self, model):
        madx = model.madx
        step = self.step
        backup = madx.globals.cmdpar[self.knob].definition
        self.apply(madx, step)
        try:
            yield step
        finally:
            madx.globals[self.knob] = backup

    def apply(self, madx, value):
        madx.globals[self.knob] *= 1+value
