"""
Dialog to set TWISS parameters.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core import wx
from madgui.core.param import ParamDialog, Bool, String, Float, Matrix


__all__ = ['TwissDialog']


class TwissDialog(ParamDialog):

    """
    Dialog to show key-value pairs.
    """

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

    @classmethod
    def connect_toolbar(cls, panel):
        model = panel.view.model
        bmp = wx.ArtProvider.GetBitmap(wx.ART_LIST_VIEW, wx.ART_TOOLBAR)
        tool = panel.toolbar.AddSimpleTool(
                wx.ID_ANY,
                bitmap=bmp,
                shortHelpString='Set TWISS initial conditions.',
                longHelpString='Set TWISS initial conditions.')
        def OnClick(event):
            dlg = cls(panel,
                      utool=model,
                      data=model.twiss_args)
            if dlg.ShowModal() == wx.ID_OK:
                model.twiss_args = dlg.data
                model.twiss()
        panel.Bind(wx.EVT_TOOL, OnClick, tool)

    def __init__(self, parent, utool, data, readonly=False):
        """
        Create an empty popup window.

        Extends wx.Dialog.__init__.
        """
        super(TwissDialog, self).__init__(
            parent=parent,
            utool=utool,
            params=self.params,
            data=data,
            readonly=readonly)
