"""
Widget to set BEAM parameters.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core import wx
from madgui.widget.param import Bool, String, Float, ParamTable

# exported symbols
__all__ = [
    'BeamWidget',
]


class BeamWidget(ParamTable):

    Title = "Beam properties"

    params = [
        String(particle="positron"),
        #String(sequence=""),   # line/sequence is passed by madgui
        Bool(bunched=True),
        Bool(radiate=True),
        Float(mass='emass'),
        Float(charge=1),
        Float(energy=1),
        Float(pc=0),
        Float(gamma=0),
        Float(ex=1, ey=1),
        Float(exn=0, eyn=0),
        Float(et=1),
        Float(sigt=0),
        Float(sige=0),
        Float(kbunch=1),
        Float(npart=1),
        Float(bcurrent=0),
        Float(freg0=0),
        Float(circ=0),
        Float(dtbyds=0),
        Float(deltap=0),
        Float(beta=0),
        Float(alfa=0),
        Float(u0=0),
        Float(qs=0),
        Float(arad=0),
        Float(bv=1),
        #Vector(pdamp=[1, 1, 2]),
        Float(n1min=-1),
    ]
