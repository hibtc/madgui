from contextlib import contextmanager


class Param:

    """Variable parameter."""

    def __init__(self, knob, step=1e-4):
        self.knob = knob
        self.step = step

    @contextmanager
    def vary(self, model):
        madx = model.madx
        step = self.step
        self.apply(madx, step)
        try:
            yield step
        finally:
            self.apply(madx, -step)

    def apply(self, madx, value):
        madx.globals[self.knob] += value

    def __repr__(self):
        return "[Δ{}={}]".format(self.knob, self.step)

    __str__ = __repr__


class Ealign:

    """Alignment error."""

    def __init__(self, select, attr, magn):
        self.select = select
        self.attr = attr
        self.magn = magn

    @contextmanager
    def vary(self, model):
        self.apply(model.madx, self.magn)
        try:
            yield self.magn
        finally:
            self.apply(model.madx, 0)

    def apply(self, madx, value):
        cmd = madx.command
        cmd.select(flag='error', clear=True)
        cmd.select(flag='error', **self.select)
        cmd.ealign(**{self.attr: value})

    def __repr__(self):
        return "[EALIGN {}->{}={}]".format(
            self.select['range'], self.attr, self.magn)

    __str__ = __repr__


class Efcomp:

    """Field error."""

    def __init__(self, select, attr, value, order=0, radius=1):
        self.select = select
        self.attr = attr
        self.value = value
        self.order = order
        self.radius = radius
        self.magn = sum(value)

    @contextmanager
    def vary(self, model):
        self.apply(model.madx, self.magn)
        try:
            yield self.magn
        finally:
            self.apply(model.madx, 0)

    def apply(self, madx, value):
        cmd = madx.command
        cmd.select(flag='error', clear=True)
        cmd.select(flag='error', **self.select)
        cmd.efcomp(
            order=self.order,
            radius=self.radius,
            **{self.attr: [v * value for v in self.value]})

    def __repr__(self):
        return "[EFCOMP {}->{}={}]".format(
            self.select['range'], self.attr, self.magn)

    __str__ = __repr__
