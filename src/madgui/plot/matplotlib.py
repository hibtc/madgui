"""
Utilities to create plots using matplotlib via the Qt5Agg backend.
"""

__all__ = [
    'PlotWidget',
    'MultiFigure',
]

from madgui.plot import mpl_backend
from matplotlib.figure import Figure
from matplotlib.ticker import AutoMinorLocator

from madgui.qt import QtCore, QtGui
from madgui.core.signal import Signal
from madgui.util.layout import VBoxLayout
from madgui.util.collections import Cache


class Toolbar(mpl_backend.NavigationToolbar2QT):

    """Toolbar that autoscales the figure when pressing the "Home" button."""

    def home(self):
        for ax in self.parent.figure.axes:
            ax.relim()
            ax.autoscale()
            ax.set_autoscale_on(False)
        self.push_current()
        self.set_history_buttons()
        self._update_view()


class PlotWidget(QtGui.QWidget):

    """
    Widget containing a matplotlib figure and toolbar. It fixes the annoying
    cursor loading quirk of the original matplotlib widget and adds an API for
    adding mouse capture buttons in the toolbar.
    """

    _updateCapture = Signal()

    def __init__(self, figure, *args, **kwargs):

        """
        Initialize figure/canvas and connect the view.

        :param TwissFigure figure: the contained figure
        :param args: positional arguments for :class:`QWidget`
        :param kwargs: keyword arguments for :class:`QWidget`
        """

        super().__init__(*args, **kwargs)

        self.figure = figure
        self.canvas = canvas = mpl_backend.FigureCanvas(figure)
        self.toolbar = toolbar = Toolbar(canvas, self)
        layout = VBoxLayout([canvas, toolbar])
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        # Needed on PyQt5 with tight_layout=True to prevent crash due to
        # singular matrix if size=0:
        canvas.setMinimumSize(QtCore.QSize(100, 100))
        # Prevent annoying busy cursor due to MPL redraws, see:
        # https://github.com/matplotlib/matplotlib/issues/9546
        canvas.set_cursor = lambda cursor: None

        # Monkey-patch MPL's mouse-capture update logic into a Qt signal:
        self._updateCapture.connect(toolbar._update_buttons_checked)
        toolbar._update_buttons_checked = self._updateCapture.emit

        self._actions = []

    def addCapture(self, mode, update):
        self._updateCapture.connect(
            lambda: update(self.toolbar._active == mode))

    def startCapture(self, mode, message):
        """
        Capture the mouse for the plot widget using the specified mode name.
        This manages the toolbar's active mouse mode and invokes the cleanup
        routine when another mode receives mouse capture (e.g. ZOOM/PAN).
        """
        if self.toolbar._active != mode:
            self.toolbar._active = mode
            self.toolbar.set_message(message)
            self.toolbar._update_buttons_checked()

    def endCapture(self, mode):
        if self.toolbar._active == mode:
            self.toolbar._active = None
            self.toolbar._update_buttons_checked()

    def addTool(self, tool):
        self._actions.append(tool)
        self.addAction(tool.action())

    def addAction(self, action):
        toolbar = self.toolbar
        try:
            before = self._insert_actions_before
        except AttributeError:
            before = self._insert_actions_before = toolbar.actions()[-1]
            toolbar.insertSeparator(before)
        toolbar.insertAction(before, action)
        # Store reference so the object doesn't get garbage collected:
        self._actions.append(action)


class MultiFigure:

    """
    A figure composed of multiple subplots with shared x-axis.

    :ivar matplotlib.figure.Figure backend_figure: composed figure
    :ivar list axes: the axes (:class:`~matplotlib.axes.Axes`)
    """

    def __init__(self, share_axes=False):
        """Create an empty matplotlib figure with multiple subplots."""
        self.backend_figure = Figure(tight_layout=True)
        self.share_axes = share_axes
        self.invalidate = self.draw.invalidate
        self.draw.updated.connect(lambda: None)     # always update
        self.axes = ()

    def set_num_axes(self, num_axes, shared=False):
        figure = self.backend_figure
        figure.clear()
        self.axes = axes = []
        if num_axes == 0:
            return
        if self.share_axes:
            axes.append(figure.add_subplot(1, 1, 1))
            axes *= num_axes
        else:
            axes.append(figure.add_subplot(num_axes, 1, 1))
            axes.extend([
                figure.add_subplot(num_axes, 1, i+1, sharex=axes[0])
                for i in range(1, num_axes)
            ])
        for ax in axes:
            ax.grid(True, axis='y')
            ax.x_name = []
            ax.y_name = []
        return axes

    @property
    def canvas(self):
        """Get the canvas."""
        return self.backend_figure.canvas

    @Cache.decorate
    def draw(self):
        """Draw the figure on its canvas."""
        self.canvas.draw()
        self.canvas.updateGeometry()

    def set_xlabel(self, label):
        """Set label on the s axis."""
        self.axes[-1].set_xlabel(label)

    def clear(self):
        """Start a fresh plot."""
        for ax in self.axes:
            ax.cla()
            ax.grid(True)
            ax.get_xaxis().set_minor_locator(AutoMinorLocator())
            ax.get_yaxis().set_minor_locator(AutoMinorLocator())
