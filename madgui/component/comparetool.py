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
from madgui.util.unit import units, strip_unit

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
        self.lines = {}
        self._visible = False
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
            self.view.hook.plot_ax.connect(self.plot_ax)

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
        return self._visible

    @visible.setter
    def visible(self, visible):
        self._visible = visible
        view = self.view
        xname = view.xname
        yname = view.yname
        if visible:
            self.plot_ax(view.axes[xname], xname)
            self.plot_ax(view.axes[yname], yname)
        else:
            self._remove_ax(xname)
            self._remove_ax(yname)
        self.view.figure.canvas.draw()

    def load_data(self):
        with self.test_file.filename() as f:
            aenv = units.mm * np.loadtxt(f, usecols=(0,1,2))
        view = self.view
        return {
            view.sname: aenv[:,0],
            view.xname: aenv[:,1],
            view.yname: aenv[:,2]
        }

    def plot_ax(self, axes, name):
        """Plot the envelope into the figure."""
        if not self.visible:
            return
        self._remove_ax(name)
        view = self.view
        envdata = self.load_data()
        sname = view.sname
        self.lines[name] = axes.plot(
            strip_unit(envdata[sname], self.view.unit[sname]),
            strip_unit(envdata[name], self.view.unit[name]),
            'k')

    def _remove_ax(self, name):
        """Remove the envelope from the figure."""
        for l in self.lines.pop(name, []):
            l.remove()
