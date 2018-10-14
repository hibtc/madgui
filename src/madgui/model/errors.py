from contextlib import contextmanager


class Param:

    """Variable parameter."""

    def __init__(self, knob, step=1e-4):
        self.knob = knob
        self.step = step

    @contextmanager
    def vary(self, model):
        knob = self.knob
        step = self.step
        madx = model.madx
        madx.globals[knob] += step
        try:
            yield step
        finally:
            madx.globals[knob] -= step


class Ealign:

    """Alignment error."""

    def __init__(self, select, attr, magn):
        self.select = select
        self.attr = attr
        self.magn = magn

    @contextmanager
    def vary(self, model):
        cmd = model.madx.command
        cmd.select(flag='error', **self.select)
        cmd.ealign(**{self.attr: self.magn})
        try:
            yield self.magn
        finally:
            cmd.ealign(**{self.attr: 0})
            cmd.select(flag='error', clear=True)


class Efcomp:

    """Field error."""

    def __init__(self, select, attrs, magn):
        self.select = select
        self.attrs = attrs
        self.magn = magn

    @contextmanager
    def vary(self, model):
        cmd = model.madx.command
        cmd.select(flag='error', **self.selectors)
        cmd.efcomp(**self.attrs)
        try:
            yield self.magn
        finally:
            cmd.efcomp(**self.attrs)
            cmd.select(flag='error', clear=True)
