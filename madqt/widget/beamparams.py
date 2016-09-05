# encoding: utf-8
"""
Widget to set BEAM parameters.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from madqt.widget.params import Bools, Strings, Floats, ParamTable


__all__ = [
    'BeamParamsWidget',
]


class BeamParamsWidget(ParamTable):

    data_key = 'beam'

    spec = [
        Strings(particle="positron"),
        #Strings(sequence=""),   # line/sequence is passed by madgui
        Bools(bunched=True),
        Bools(radiate=True),
        Floats(mass='emass'),
        Floats(charge=1),
        Floats(energy=1),
        Floats(pc=0),
        Floats(gamma=0),
        Floats(ex=1, ey=1),
        Floats(exn=0, eyn=0),
        Floats(et=1),
        Floats(sigt=0),
        Floats(sige=0),
        Floats(kbunch=1),
        Floats(npart=1),
        Floats(bcurrent=0),
        Floats(freg0=0),
        Floats(circ=0),
        Floats(dtbyds=0),
        Floats(deltap=0),
        Floats(beta=0),
        Floats(alfa=0),
        Floats(u0=0),
        Floats(qs=0),
        Floats(arad=0),
        Floats(bv=1),
        #Vector(pdamp=[1, 1, 2]),
        Floats(n1min=-1),
    ]

    def __init__(self, utool, *args, **kwargs):
        super(BeamParamsWidget, self).__init__(self.spec, utool, *args, **kwargs)
