"""
Utilities to create plots using matplotlib via the Qt5Agg backend.
"""

from collections import namedtuple

from madgui.qt import QtCore, QtGui      # import Qt before matplotlib!

import matplotlib as mpl
mpl.use('Qt5Agg')                       # select before mpl.backends import!
import matplotlib.backends.backend_qt5agg as mpl_backend

from matplotlib.figure import Figure
from matplotlib.ticker import AutoMinorLocator

from madgui.core.base import Signal, Cache
from madgui.util.layout import VBoxLayout


__all__ = [
    'PlotWidget',
    'MultiFigure',
]


Triple = namedtuple('Triple', ['x', 'y', 's'])

MouseEvent = namedtuple('MouseEvent', [
    'button', 'x', 'y', 'axes', 'elem', 'guiEvent'])

KeyboardEvent = namedtuple('KeyboardEvent', [
    'key', 'guiEvent'])


class PlotWidget(QtGui.QWidget):

    """
    Widget containing a matplotlib figure.
    """

    buttonPress = Signal(MouseEvent)
    keyPress = Signal(KeyboardEvent)
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
        self.canvas = canvas = mpl_backend.FigureCanvas(figure.backend_figure)
        self.toolbar = toolbar = mpl_backend.NavigationToolbar2QT(canvas, self)
        layout = VBoxLayout([canvas, toolbar])
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        # Needed on PyQt5 with tight_layout=True to prevent crash due to
        # singular matrix if size=0:
        canvas.setMinimumSize(QtCore.QSize(100, 100))

        self._cid_mouse = canvas.mpl_connect(
            'button_press_event', self.onButtonPress)
        self._cid_key = canvas.mpl_connect(
            'key_press_event', self.onKeyPress)

        # Monkey-patch MPL's mouse-capture update logic into a Qt signal:
        self._updateCapture.connect(toolbar._update_buttons_checked)
        toolbar._update_buttons_checked = self._updateCapture.emit

        self._actions = []

    def set_scene(self, scene):
        self.scene = scene

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

    def onButtonPress(self, mpl_event):
        # translate event to matplotlib-oblivious API
        if mpl_event.inaxes is None:
            return
        axes = mpl_event.inaxes
        xpos = mpl_event.xdata * axes.x_unit
        ypos = mpl_event.ydata * axes.y_unit
        elem = self.scene.model.get_element_by_mouse_position(axes, xpos)
        event = MouseEvent(mpl_event.button, xpos, ypos,
                           axes, elem, mpl_event.guiEvent)
        self.buttonPress.emit(event)

    def onKeyPress(self, mpl_event):
        event = KeyboardEvent(mpl_event.key, mpl_event.guiEvent)
        self.keyPress.emit(event)


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
        self.invalidate = Cache(self.draw).invalidate
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
            for i in range(1, num_axes):
                axes.append(figure.add_subplot(num_axes, 1, i+1, sharex=axes[0]))
        return axes

    @property
    def canvas(self):
        """Get the canvas."""
        return self.backend_figure.canvas

    def autoscale(self):
        for ax in self.axes:
            _autoscale_axes(ax)

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
            _clear_ax(ax)

    def connect(self, *args):
        for ax in self.axes:
            ax.callbacks.connect(*args)

    def disconnect(self, *args):
        for ax in self.axes:
            ax.callbacks.disconnect(*args)


def _clear_ax(ax):
    """Clear a single :class:`matplotlib.axes.Axes` instance."""
    ax.cla()
    ax.grid(True)
    ax.get_xaxis().set_minor_locator(AutoMinorLocator())
    ax.get_yaxis().set_minor_locator(AutoMinorLocator())


def _autoscale_axes(axes):
    """Autoscale a :class:`matplotlib.axes.Axes` to its contents."""
    axes.relim()
    axes.autoscale()
