"""
Widgets to set TWISS parameters.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.widget.param import ParamTable, Bool, String, Float, Matrix

# exported symbols
__all__ = [
    'TwissWidget',
]


class TwissWidget(ParamTable):

    """
    Widget to show key-value pairs.
    """

    Title = "Set TWISS values"

    # TODO:
    # - exclude more parameters (for most of these parameters, I actually
    #   don't know whether it makes sense to include them here)
    # - for excluded parameters show info string
    # - dynamically determine better default values
    params = [
        Float(betx=0, bety=0),
        Float(alfx=0, alfy=0),
        Float(mux=0, muy=0),
        Float(x=0, y=0),
        Float(t=0),
        Float(pt=0),
        Float(px=0, py=0),
        Float(dpx=0, dpy=0),
        Float(wx=0, wy=0),
        Float(phix=0, phiy=0),
        Float(dmux=0, dmuy=0),
        Float(ddx=0, ddy=0),
        Float(ddpx=0, ddpy=0),
        Matrix(r=[(0, 0),
                  (0, 0)]),
        Float(energy=0),
        Bool(chrom=True),
        String(file=""),
        String(save=""),
        String(table="twiss"),
        String(beta0=""),
        Matrix(re=[(1, 0, 0, 0, 0, 0),
                   (0, 1, 0, 0, 0, 0),
                   (0, 0, 1, 0, 0, 0),
                   (0, 0, 0, 1, 0, 0),
                   (0, 0, 0, 0, 1, 0),
                   (0, 0, 0, 0, 0, 1)]),
        Bool(centre=True),
        Bool(ripken=True),
        Bool(sectormap=True),
        String(sectortable=""),
        String(sectorfile="sectormap"),
        Bool(rmatrix=True),
        #String(sequence=""),   # line/sequence is passed by madgui
        #String(line=""),       # line/sequence is passed by madgui
        #String(range=""),      # range is passed by madgui
        String(useorbit=""),
        String(keeporbit=""),
        Float(tolerance=0),
        String(deltap=""),
        #Bool(notable=True),    # madgui always needs table
    ]

    def Validate(self):
        """
        Validate the input.

        This checks that the current dialog state satisfies the minimal
        requirements on TWISS initial conditions, which is:

            - alpha, beta must be given
            - betx, bety must be greater than zero
        """
        alfx = self.GetRowValue('alfx')
        alfy = self.GetRowValue('alfy')
        betx = self.GetRowValue('betx')
        bety = self.GetRowValue('bety')
        if None in (alfx, alfy, betx, bety):
            return False
        if betx <= 0 or bety <= 0:
            return False
        return True
