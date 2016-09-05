# encoding: utf-8
"""
Widgets to set TWISS parameters.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from madqt.widget.params import ParamTable, Bools, Strings, Floats, Matrix


__all__ = [
    'TwissParamsWidget',
]


class TwissParamsWidget(ParamTable):

    """
    Widget to show key-value pairs.
    """

    data_key = 'twiss'

    # TODO:
    # - exclude more parameters (for most of these parameters, I actually
    #   don't know whether it makes sense to include them here)
    # - for excluded parameters show info string
    # - dynamically determine better default values
    spec = [
        Floats(betx=0, bety=0),
        Floats(alfx=0, alfy=0),
        Floats(mux=0, muy=0),
        Floats(x=0, y=0),
        Floats(t=0),
        Floats(pt=0),
        Floats(px=0, py=0),
        Floats(dpx=0, dpy=0),
        Floats(wx=0, wy=0),
        Floats(phix=0, phiy=0),
        Floats(dmux=0, dmuy=0),
        Floats(ddx=0, ddy=0),
        Floats(ddpx=0, ddpy=0),
        Matrix(r=[(0, 0),
                  (0, 0)]),
        Floats(energy=0),
        Bools(chrom=True),
        Strings(file=""),
        Strings(save=""),
        Strings(table="twiss"),
        Strings(beta0=""),
        Matrix(re=[(1, 0, 0, 0, 0, 0),
                   (0, 1, 0, 0, 0, 0),
                   (0, 0, 1, 0, 0, 0),
                   (0, 0, 0, 1, 0, 0),
                   (0, 0, 0, 0, 1, 0),
                   (0, 0, 0, 0, 0, 1)]),
        Bools(centre=True),
        Bools(ripken=True),
        Bools(sectormap=True),
        Strings(sectortable=""),
        Strings(sectorfile="sectormap"),
        Bools(rmatrix=True),
        #Strings(sequence=""),   # line/sequence is passed by madqt
        #Strings(line=""),       # line/sequence is passed by madqt
        #Strings(range=""),      # range is passed by madqt
        Strings(useorbit=""),
        Strings(keeporbit=""),
        Floats(tolerance=0),
        Strings(deltap=""),
        #Bools(notable=True),    # madqt always needs table
    ]

    def __init__(self, utool, *args, **kwargs):
        super(TwissParamsWidget, self).__init__(self.spec, utool, *args, **kwargs)
