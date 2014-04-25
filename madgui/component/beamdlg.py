"""
Dialog to set BEAM parameters.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core import wx
from madgui.core.param import Bool, String, Float, ParamDialog


class BeamDialog(ParamDialog):

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

    @classmethod
    def connect_toolbar(cls, panel):
        model = panel.view.model
        bmp = wx.ArtProvider.GetBitmap(wx.ART_HELP_SETTINGS, wx.ART_TOOLBAR)
        tool = panel.toolbar.AddSimpleTool(
                wx.ID_ANY,
                bitmap=bmp,
                shortHelpString='Set BEAM.',
                longHelpString='Set BEAM.')
        def OnClick(event):
            dlg = cls(panel, model.beam)
            if dlg.ShowModal() == wx.ID_OK:
                model.beam = dlg.data
                model.twiss()
        panel.Bind(wx.EVT_TOOL, OnClick, tool)

    def __init__(self, parent, data, readonly=False):
        """
        Create an empty popup window.

        Extends wx.Dialog.__init__.
        """
        super(BeamDialog, self).__init__(
            parent=parent,
            params=self.params,
            data=data,
            readonly=readonly)
