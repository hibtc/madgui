# encoding: utf-8
"""
Utilities to create plots using matplotlib via the Qt4Agg backend.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from collections import namedtuple

from madqt.qt import QtCore, QtGui, QT_API  # import Qt before matplotlib!

import matplotlib as mpl
if QT_API == 'pyqt5':
    mpl.use('Qt5Agg')                       # select before mpl.backends import!
    import matplotlib.backends.backend_qt5agg as mpl_backend
elif QT_API == 'pyqt':
    mpl.use('Qt4Agg')                       # select before mpl.backends import!
    import matplotlib.backends.backend_qt4agg as mpl_backend
else:
    raise NotImplementedError("Unsupported Qt API: {}".format(QT_API))

from matplotlib.figure import Figure
from matplotlib.ticker import AutoMinorLocator

from madqt.core.base import Signal
from madqt.util.layout import VBoxLayout


__all__ = [
    'PlotWidget',
    'FigurePair',
    'Curve',
]


Pair = namedtuple('Pair', ['x', 'y'])
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

        super(PlotWidget, self).__init__(*args, **kwargs)

        self.figure = figure
        self.canvas = canvas = mpl_backend.FigureCanvas(figure.backend_figure)
        self.toolbar = toolbar = mpl_backend.NavigationToolbar2QT(canvas, self)
        self.setLayout(VBoxLayout([canvas, toolbar]))

        self._cid_mouse = canvas.mpl_connect(
            'button_press_event', self.onButtonPress)
        self._cid_key = canvas.mpl_connect(
            'key_press_event', self.onKeyPress)

        # Monkey-patch MPL's mouse-capture update logic into a Qt signal:
        self._updateCapture.connect(toolbar._update_buttons_checked)
        toolbar._update_buttons_checked = self._updateCapture.emit

        # setup the figure
        self._actions = []
        figure.attach(self, canvas, toolbar)
        figure.plot()

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
        name = mpl_event.inaxes.twiss_name
        xpos = mpl_event.xdata * self.figure.unit['s']
        ypos = mpl_event.ydata * self.figure.unit[name]
        elem = self.figure.segment.element_by_position(xpos)
        event = MouseEvent(mpl_event.button, xpos, ypos,
                           axes, elem, mpl_event.guiEvent)
        self.buttonPress.emit(event)

    def onKeyPress(self, mpl_event):
        event = KeyboardEvent(mpl_event.key, mpl_event.guiEvent)
        self.keyPress.emit(event)


class FigurePair(object):

    """
    A figure composed of two subplots with shared s-axis.

    :ivar matplotlib.figure.Figure backend_figure: composed figure
    :ivar matplotlib.axes.Axes axx: upper subplot
    :ivar matplotlib.axes.Axes axy: lower subplot
    """

    def __init__(self):
        """Create an empty matplotlib figure with two subplots."""
        self.backend_figure = figure = Figure()
        axx = figure.add_subplot(211)
        axy = figure.add_subplot(212, sharex=axx)
        self.axes = Pair(axx, axy)

    @property
    def canvas(self):
        """Get the canvas."""
        return self.backend_figure.canvas

    def draw(self):
        """Draw the figure on its canvas."""
        _autoscale_axes(self.axes.x)
        _autoscale_axes(self.axes.y)
        canvas = self.backend_figure.canvas
        canvas.draw()
        canvas.updateGeometry()

    def set_slabel(self, label):
        """Set label on the s axis."""
        self.axes.y.set_xlabel(label)

    def clear(self):
        """Start a fresh plot."""
        _clear_ax(self.axes.x)
        _clear_ax(self.axes.y)


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


class Curve(object):

    """Plot a TWISS parameter curve segment into a 2D figure."""

    def __init__(self, axes, get_xdata, get_ydata, style):
        """Store meta data."""
        self.axes = axes
        self.get_xdata = get_xdata
        self.get_ydata = get_ydata
        self.style = style
        self.line = None

    def plot(self):
        """Make one subplot."""
        xdata = self.get_xdata()
        ydata = self.get_ydata()
        self.axes.set_xlim(xdata[0], xdata[-1])
        self.line = self.axes.plot(xdata, ydata, **self.style)[0]

    def update(self):
        """Update the y values for one subplot."""
        self.line.set_ydata(self.get_ydata())

    def remove(self):
        """Disconnect update events."""
        if self.line is not None:
            self.line.remove()
            self.line = None
