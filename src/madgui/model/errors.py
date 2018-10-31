from contextlib import contextmanager


class BaseError:

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


class Param(BaseError):

    """Variable parameter."""

    def __init__(self, knob, step=1e-4, madx=None):
        super().__init__(step)
        self.knob = knob
        if madx is not None:
            self.set_base(madx)

    def set_base(self, madx):
        self.base = madx.globals[self.knob]

    def apply(self, madx, value):
        madx.globals[self.knob] += value

    def __repr__(self):
        return "[Δ{}={}]".format(self.knob, self.step)


class Ealign(BaseError):

    """Alignment error."""

    def __init__(self, select, attr, step):
        super().__init__(step)
        self.select = select
        self.attr = attr

    def apply(self, madx, value):
        cmd = madx.command
        cmd.select(flag='error', clear=True)
        cmd.select(flag='error', **self.select)
        cmd.ealign(**{self.attr: value})

    def __repr__(self):
        return "[EALIGN {}->{}={}]".format(
            self.select['range'], self.attr, self.step)


class Efcomp(BaseError):

    """Field error."""

    def __init__(self, select, attr, value, order=0, radius=1):
        super().__init__(sum(value))
        self.select = select
        self.attr = attr
        self.value = value
        self.order = order
        self.radius = radius

    def apply(self, madx, value):
        cmd = madx.command
        cmd.select(flag='error', clear=True)
        cmd.select(flag='error', **self.select)
        cmd.efcomp(**{
            'order': self.order,
            'radius': self.radius,
            self.attr: [v * value for v in self.value],
        })

    def __repr__(self):
        return "[EFCOMP {}->{}={}]".format(
            self.select['range'], self.attr, self.step)


class ElemAttr(BaseError):

    """Variable parameter."""

    def __init__(self, elem, attr, step=1e-4, madx=None):
        super().__init__(step)
        self.elem = elem
        self.attr = attr
        if madx is not None:
            self.set_base(madx)

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

    def __repr__(self):
        return "[Δ{}->{}={}]".format(self.elem, self.attr, self.step)
