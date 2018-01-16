"""
Implementations covering the MAD-X backend for accessing element properties.
"""

from . import api

# TODO: adapt to bmad
# - multipole: k0l/…
# - kicker: hkick/vkick


# Dipole

class Dipole(api.NoConversion):

    standard_keys = backend_keys = ['angle']

    # TODO: DIPOLEs (+MULTIPOLEs) rotate the reference orbit, which is
    # probably not intended... use YROTATION?


class MultipoleNDP(api.ElementBackendConverter):

    standard_keys = ['angle']
    backend_keys = ['knl']

    def to_standard(self, values):
        return {'angle': values['knl'][0]}

    def to_backend(self, values):
        return {'knl': [values['angle']]}


class MultipoleSDP(api.ElementBackendConverter):

    standard_keys = ['angle']
    backend_keys = ['ksl']

    def to_standard(self, values):
        return {'angle': values['ksl'][0]}

    def to_backend(self, values):
        return {'ksl': [values['angle']]}


# Quadrupole

class Quadrupole(api.ElementBackendConverter):

    standard_keys = ['kL']
    backend_keys = ['k1']
    # TODO: handle k1s?

    def __init__(self, l):
        self._l = l

    def to_standard(self, values):
        return {'kL': values['k1'] * self._l}

    def to_backend(self, values):
        return {'k1': values['kL'] / self._l}


class MultipoleNQP(api.ElementBackendConverter):

    standard_keys = ['kL']
    backend_keys = ['knl']

    def to_standard(self, values):
        return {'kL': values['knl'][1]}

    def to_backend(self, values):
        return {'knl': [0, values['kL']]}


class MultipoleSQP(api.ElementBackendConverter):

    standard_keys = ['kL']
    backend_keys = ['ksl']

    def to_standard(self, values):
        return {'kL': values['ksl'][1]}

    def to_backend(self, values):
        return {'ksl': [0, values['kL']]}


# Solenoid

class Solenoid(api.NoConversion):
    standard_keys = backend_keys = ['ks']


# Kicker

class KickerBase(api.ElementBackendConverter):
    standard_keys = ['angle']
    backend_keys = ['kick']

    def to_standard(self, values):
        return {'angle': values['kick']}

    def to_backend(self, values):
        return {'kick': values['angle']}


class HKicker(KickerBase):
    pass

class VKicker(KickerBase):
    pass

