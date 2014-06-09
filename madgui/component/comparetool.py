# encoding: utf-8
"""
Matching tool for a :class:`LineView` instance.
"""

# force new style imports
from __future__ import absolute_import

# scipy
import numpy as np

# internal
from madgui.core import wx
from madgui.util.unit import units, stripunit

# exported symbols
__all__ = ['CompareTool']


class CompareTool(object):

    """
    View component to display mirko envelope for comparison.

    Draws the mirko envelope into a LineView figure whenever that figure
    is replotted.
    """

    def __init__(self, panel):
        """
        Create a mirko envelope display component.

        The envelope is NOT visible by default.
        """
        self.model = panel.view.model
        self.view = panel.view
        self.lines = None
        if self.test_file:
            # connect to toolbar
            bmp = wx.ArtProvider.GetBitmap(wx.ART_GO_HOME, wx.ART_TOOLBAR)
            tool = panel.toolbar.AddCheckTool(
                    wx.ID_ANY,
                    bitmap=bmp,
                    shortHelp='Show MIRKO envelope',
                    longHelp='Show MIRKO envelope for comparison. The envelope is computed for the default parameters.')
            panel.Bind(wx.EVT_TOOL, self.OnMirkoClick, tool)
            # subscribe to plotting
            self.view.hook.plot.connect(self.redraw)

    def OnMirkoClick(self, event):
        """Invoked when user clicks Mirko-Button"""
        self.visible = event.IsChecked()

    @property
    def test_file(self):
        """Get the envelope file."""
        model = self.model.model
        if not model:
            return None
        optic = model._mdef['optics'][model._active['optic']]
        if 'test' in optic:
            return model.mdata.get_by_dict(optic['test'])

    @property
    def visible(self):
        """Visibility state of the envelope."""
        return self.lines is not None

    @visible.setter
    def visible(self, value):
        if value:
            self._plot()
        else:
            self._remove()

    def redraw(self):
        """Redraw the envelope if set to visible."""
        if self.visible:
            self._plot()

    def _plot(self):
        """Plot the envelope into the figure."""
        with self.test_file.filename() as f:
            aenv = units.mm * np.loadtxt(f, usecols=(0,1,2))
        envdata = {
            's': aenv[:,0],
            'x': aenv[:,1],
            'y': aenv[:,2]
        }
        self.lines = {
            'x': self.view.axes['envx'].plot(
                stripunit(envdata['s'], self.view.unit['s']),
                stripunit(envdata['x'], self.view.unit['envx']),
                'k'),
            'y': self.view.axes['envy'].plot(
                stripunit(envdata['s'], self.view.unit['s']),
                stripunit(envdata['y'], self.view.unit['envy']),
                'k')
        }
        self.view.figure.canvas.draw()

    def _remove(self):
        """Remove the envelope from the figure."""
        if self.lines:
            # self.view.axes['x'].lines.remove(self.lines['x'])
            # self.view.axes['y'].lines.remove(self.lines['y'])
            for l in self.lines['x']:
                l.remove()
            for l in self.lines['y']:
                l.remove()
            self.lines = None
            self.view.figure.canvas.draw()

