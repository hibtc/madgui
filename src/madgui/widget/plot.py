"""
Utilities to create plots using matplotlib via the Qt5Agg backend.
"""

__all__ = [
    'Toolbar',
    'PlotWidget',
]

import matplotlib.backends.backend_qt5agg as mpl_backend
from matplotlib.figure import Figure
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QWidget

from madgui.util.signal import Signal
from madgui.util.layout import VBoxLayout


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


class PlotWidget(QWidget):

    """
    Widget containing a matplotlib figure and toolbar. It fixes the annoying
    cursor loading quirk of the original matplotlib widget and adds an API for
    adding mouse capture buttons in the toolbar.
    """

    _updateCapture = Signal()

    def __init__(self, figure=None, *args, **kwargs):

        """
        Initialize figure/canvas and connect the view.

        :param TwissFigure figure: the contained figure
        :param args: positional arguments for :class:`QWidget`
        :param kwargs: keyword arguments for :class:`QWidget`
        """

        super().__init__(*args, **kwargs)

        self.figure = figure or Figure(tight_layout=True)
        self.canvas = canvas = mpl_backend.FigureCanvas(figure)
        self.toolbar = toolbar = Toolbar(canvas, self)
        self.setLayout(VBoxLayout([canvas, toolbar], tight=True))
        # Needed on PyQt5 with tight_layout=True to prevent crash due to
        # singular matrix if size=0:
        canvas.setMinimumSize(QSize(100, 100))
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
