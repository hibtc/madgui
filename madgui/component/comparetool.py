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
from madgui.util import unit

# exported symbols
__all__ = ['CompareTool']


def match_metadata(all_metadata, sequence, col_names):
    """
    Find suitable match for sequence/optic/range/columns in metadata.
    
    :param list all_metadata: all metadata entries for the model
    :param str sequence: sequence name to be searched for
    :param list col_names: column names to be searched for
    :returns: matched metadata
    :rtype: dict

    TODO: Add optic/range matching
    """
    for review in all_metadata:
        if review['sequence'] != sequence:
            continue
        columns = review['columns']
        if all(col in columns for col in col_names):
            return review
    raise ValueError()


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
        self._view = view = panel.view
        self._model = model = view.model
        self._lines = {}
        self._visible = False
        self._metadata = None

        cpymad_model = model.model
        if not cpymad_model:
            return

        all_metadata = cpymad_model.mdef['review']
        col_names = [view.sname, view.xname, view.yname]
        try:
            metadata = match_metadata(all_metadata, model.name, col_names)
        except ValueError:
            return
        self._metadata = metadata

        # connect to toolbar
        bmp = wx.ArtProvider.GetBitmap(wx.ART_GO_HOME, wx.ART_TOOLBAR)
        tool = panel.toolbar.AddCheckTool(
                wx.ID_ANY,
                bitmap=bmp,
                shortHelp='Show MIRKO envelope',
                longHelp='Show MIRKO envelope for comparison. The envelope is computed for the default parameters.')
        panel.Bind(wx.EVT_TOOL, self.on_click, tool)
        # subscribe to plotting
        view.hook.plot_ax.connect(self.plot_ax)

    def on_click(self, event):
        """Invoked when user clicks Mirko-Button"""
        self.visible = event.IsChecked()

    @property
    def test_file(self):
        """Get the envelope file."""
        return self._model.model.mdata.get_by_dict(self._metadata['file'])

    @property
    def visible(self):
        """Visibility state of the envelope."""
        return self._visible

    @visible.setter
    def visible(self, visible):
        """Set visibility."""
        self._visible = visible
        view = self._view
        xname = view.xname
        yname = view.yname
        if visible:
            self.plot_ax(view.axes[xname], xname)
            self.plot_ax(view.axes[yname], yname)
        else:
            self._remove_ax(xname)
            self._remove_ax(yname)
        self._view.figure.canvas.draw()

    def load_data(self, name):
        """Load envelope from file."""
        column_info = self._metadata['columns']
        scol = column_info['s']
        ycol = column_info[name]
        with self.test_file.filename() as f:
            aenv = np.loadtxt(f, usecols=(scol['column'], ycol['column']))
        return {
            's': unit.from_config(scol['unit']) * aenv[:,0],
            name: unit.from_config(ycol['unit']) * aenv[:,1],
        }

    def plot_ax(self, axes, name):
        """Plot the envelope into the figure."""
        if not self.visible:
            return
        self._remove_ax(name)
        view = self._view
        envdata = self.load_data(name)
        sname = view.sname
        self._lines[name] = axes.plot(
            unit.strip_unit(envdata[sname], view.unit[sname]),
            unit.strip_unit(envdata[name], view.unit[name]),
            'k')

    def _remove_ax(self, name):
        """Remove the envelope from the figure."""
        for l in self._lines.pop(name, []):
            l.remove()
