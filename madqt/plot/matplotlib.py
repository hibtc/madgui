# encoding: utf-8
"""
Utilities to create plots using matplotlib via the Qt4Agg backend.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from collections import namedtuple
from functools import partial

from madqt.qt import QtCore, QtGui, Qt, QT_API  # import Qt before matplotlib!
from madqt.util.qt import notifyCloseEvent, notifyEvent

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

from madqt.core.unit import units, strip_unit, get_unit_label, get_raw_label
from madqt.core.base import Object, Signal
from madqt.util.layout import VBoxLayout


__all__ = [
    'PlotWidget',
    'FigurePair',
    'TwissFigure',
    'ElementIndicators',
]


Pair = namedtuple('Pair', ['x', 'y'])


class PlotWidget(QtGui.QWidget):

    """
    Widget containing a matplotlib figure.
    """

    def __init__(self, figure, *args, **kwargs):

        """
        Initialize figure/canvas and connect the view.

        :param TwissFigure figure: the contained figure
        :param args: positional arguments for :class:`QWidget`
        :param kwargs: keyword arguments for :class:`QWidget`
        """

        super(PlotWidget, self).__init__(*args, **kwargs)

        self.figure = figure
        self.canvas = mpl_backend.FigureCanvas(figure.mpl_figure)
        self.toolbar = mpl_backend.NavigationToolbar2QT(self.canvas, self)
        self.figure.plot()

        self.setLayout(VBoxLayout([self.canvas, self.toolbar]))

        self._active = self.toolbar._active
        self._uncapture = None
        self._old_update_buttons = self.toolbar._update_buttons_checked
        self.toolbar._update_buttons_checked = self._update_buttons_checked

    def captureMouse(self, mode, message, deactivate):
        """
        Capture the mouse for the plot widget using the specified mode name.
        This manages the toolbar's active mouse mode and invokes the cleanup
        routine when another mode receives mouse capture (e.g. ZOOM/PAN).
        """
        self.toolbar._active = mode
        self.toolbar.set_message(message)
        self.toolbar._update_buttons_checked()
        self._uncapture = deactivate

    def _update_buttons_checked(self):
        if self.toolbar._active != self._active:
            self._active = self.toolbar._active
            if self._uncapture is not None:
                self._uncapture()
                self._uncapture = None
        self._old_update_buttons()

    def addAction(self, icon, text):
        if isinstance(icon, QtGui.QStyle.StandardPixmap):
            icon =  self.style().standardIcon(icon)
        action = QtGui.QAction(self.toolbar)
        action.setText(text)
        action.setIcon(icon)
        self.insertAction(action)
        return action

    def insertAction(self, action):
        toolbar = self.toolbar
        try:
            before = self._insert_actions_before
        except AttributeError:
            before = self._insert_actions_before = toolbar.actions()[-1]
            toolbar.insertSeparator(before)
        toolbar.insertAction(before, action)


class FigurePair(object):

    """
    A figure composed of two subplots with shared s-axis.

    :ivar matplotlib.figure.Figure mpl_figure: composed figure
    :ivar matplotlib.axes.Axes axx: upper subplot
    :ivar matplotlib.axes.Axes axy: lower subplot
    """

    def __init__(self):
        """Create an empty matplotlib figure with two subplots."""
        self.mpl_figure = figure = Figure()
        axx = figure.add_subplot(211)
        axy = figure.add_subplot(212, sharex=axx)
        self.axes = Pair(axx, axy)

    @property
    def canvas(self):
        """Get the canvas."""
        return self.mpl_figure.canvas

    def draw(self):
        """Draw the figure on its canvas."""
        _autoscale_axes(self.axes.x)
        _autoscale_axes(self.axes.y)
        canvas = self.mpl_figure.canvas
        canvas.draw()
        canvas.updateGeometry()

    def set_slabel(self, label):
        """Set label on the s axis."""
        self.axes.y.set_xlabel(label)

    def clear(self):
        """Start a fresh plot."""
        _clear_ax(self.axes.x)
        _clear_ax(self.axes.y)


class TwissFigure(object):

    """A figure containing some X/Y twiss parameters."""

    @classmethod
    def create(cls, universe, frame, basename):
        """Create a new figure as a page in the notebook frame."""
        if not universe.segment:
            return
        figure = cls(universe.segment, basename, frame.config['line_view'])
        #panel = frame.AddView(figure, figure.title)
        return figure

    def __init__(self, segment, basename, config):

        # create figure
        self.figure = figure = FigurePair()
        self.segment = segment
        self.config = config
        self.basename = basename

        self.title = config['title'][basename]
        self.sname = sname = 's'
        self.names = Pair(basename+'x', basename+'y')

        # plot style
        self.label = config['label']
        unit_names = config['unit']
        all_axes_names = (self.sname,) + self.names
        self.unit = {col: getattr(units, unit_names[col])
                     for col in all_axes_names}

        axes = self.figure.axes

        # Tune the builtin coord status message on the toolbar:
        axes.x.format_coord = partial(self.format_coord, self.names.x)
        axes.y.format_coord = partial(self.format_coord, self.names.y)

        # create scene
        elements_style = config['element_style']
        self.scene_graph = SceneGraph([])
        self.add_twiss_curve(self.basename)
        self.indicators = SceneGraph([
            ElementIndicators(axes.x, self, elements_style),
            ElementIndicators(axes.y, self, elements_style),
        ])

        # subscribe for updates
        self.segment.updated.connect(self.update)

    @property
    def mpl_figure(self):
        return self.figure.mpl_figure

    def remove(self):
        self.scene_graph.remove()
        self.segment.updated.disconnect(self.update)

    def format_coord(self, name, x, y):
        unit = self.unit
        elem = self.segment.element_by_position(x * unit['s'])
        # TODO: in some cases, it might be necessary to adjust the
        # precision to the displayed xlim/ylim.
        coord_fmt = "{0}={1:.6f}{2}".format
        parts = [coord_fmt('s', x, get_raw_label(unit['s'])),
                 coord_fmt(name, y, get_raw_label(unit[name]))]
        if elem and 'name' in elem:
            parts.insert(0, 'elem={0}'.format(elem['name']))
        return ', '.join(parts)

    def get_label(self, name):
        return self.label[name] + ' ' + get_unit_label(self.unit[name])

    def plot(self):
        """Replot from clean state."""
        fig = self.figure
        fig.clear()
        fig.axes.x.set_ylabel(self.get_label(self.names.x))
        fig.axes.y.set_ylabel(self.get_label(self.names.y))
        fig.set_slabel(self.get_label(self.sname))
        self.scene_graph.plot()
        fig.draw()

    def update(self):
        """Update existing plot after TWISS recomputation."""
        self.scene_graph.update()
        self.figure.draw()

    def get_axes_name(self, axes):
        return self.names[self.figure.axes.index(axes)]

    def get_conjugate(self, name):
        return self.names[1-self.names.index(name)]

    def add_twiss_curve(self, basename, sname='s'):
        """
        Add an X/Y pair of lines of TWISS parameters into the figure.

        :param str basename: stem of the parameter name, e.g. 'bet'
        :param str sname: data name of the shared s-axis
        """
        xname = basename + 'x'
        yname = basename + 'y'
        style = self.config['curve_style']
        axes = self.figure.axes
        get_sdata = partial(self.get_float_data, sname)
        get_xdata = partial(self.get_float_data, xname)
        get_ydata = partial(self.get_float_data, yname)
        self.scene_graph.items.extend([
            Curve(axes.x, get_sdata, get_xdata, style['x']),
            Curve(axes.y, get_sdata, get_ydata, style['y']),
        ])

    def get_float_data(self, name):
        """Get data for the given parameter from segment."""
        return strip_unit(self.segment.tw[name], self.unit[name])

    @property
    def show_indicators(self):
        return self.indicators in self.scene_graph.items

    @show_indicators.setter
    def show_indicators(self, show):
        if show == self.show_indicators:
            return
        if show:
            self.scene_graph.items.append(self.indicators)
        else:
            self.scene_graph.items.remove(self.indicators)


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


class SceneGraph(object):

    def __init__(self, items):
        self.items = items

    def remove(self):
        for item in self.items:
            item.remove()

    def plot(self):
        for item in self.items:
            item.plot()

    def update(self):
        for item in self.items:
            item.update()


class Curve(object):

    """Plot a TWISS parameter curve segment into a 2D figure."""

    def __init__(self, axes, get_xdata, get_ydata, style):
        """Store meta data."""
        self.axes = axes
        self.get_xdata = get_xdata
        self.get_ydata = get_ydata
        self.style = style
        self.line = None

    def remove(self):
        """Disconnect update events."""
        if self.line is not None:
            self.line.remove()
            self.line = None

    def update(self):
        """Update the y values for one subplot."""
        self.line.set_ydata(self.get_ydata())

    def plot(self):
        """Make one subplot."""
        xdata = self.get_xdata()
        ydata = self.get_ydata()
        self.axes.set_xlim(xdata[0], xdata[-1])
        self.line = self.axes.plot(xdata, ydata, **self.style)[0]


class ElementIndicators(object):

    """
    Draw beam line elements (magnets etc) into a :class:`TwissFigure`.
    """

    def __init__(self, axes, figure, style):
        self.axes = axes
        self.figure = figure
        self.style = style
        self.lines = []

    @property
    def s_unit(self):
        return self.figure.unit[self.figure.sname]

    @property
    def elements(self):
        return self.figure.segment.elements

    def remove(self):
        for line in self.lines:
            line.remove()
        self.lines.clear()

    def plot(self):
        """Draw the elements into the canvas."""
        axes = self.axes
        s_unit = self.s_unit
        for elem in self.elements:
            elem_type = self.get_element_type(elem)
            if elem_type is None:
                continue
            patch_x = strip_unit(elem['at'], s_unit)
            if strip_unit(elem['l']) != 0:
                patch_w = strip_unit(elem['l'], s_unit)
                line = axes.axvspan(patch_x, patch_x + patch_w, **elem_type)
            else:
                line = axes.vlines(patch_x, **elem_type)
            self.lines.append(line)

    def update(self):
        pass

    def get_element_type(self, elem):
        """Return the element type name used for properties like coloring."""
        if 'type' not in elem or 'at' not in elem:
            return None
        type_name = elem['type'].lower()
        focussing = None
        if type_name == 'quadrupole':
            focussing = strip_unit(elem['k1']) > 0
        elif type_name == 'sbend':
            focussing = strip_unit(elem['angle']) > 0
        if focussing is not None:
            if focussing:
                type_name = 'f-' + type_name
            else:
                type_name = 'd-' + type_name
        return self.style.get(type_name)


class SelectTool(object):

    """
    Opens detail popups when clicking on an element.
    """

    def __init__(self, plot_widget):
        """Add toolbar tool to panel and subscribe to capture events."""
        self._cid_mouse = None
        self._cid_key = None
        self.plot_widget = plot_widget
        self.segment = plot_widget.figure.segment
        self.figure = plot_widget.figure
        self.toolbar = plot_widget.toolbar

        self.add_toolbar_action()

        # Store a reference so we don't get garbage collected:
        plot_widget._select_tool = self

        # List of existing info boxes
        self._info_boxes = []

    def add_toolbar_action(self):
        action = self.action = self.plot_widget.addAction(
            icon=QtGui.QStyle.SP_MessageBoxInformation,
            text='Show info for individual elements')
        action.setCheckable(True)
        action.triggered.connect(self.onToolClicked)

    def onToolClicked(self, checked):
        """Invoked when user clicks Mirko-Button"""
        if checked:
            self.startSelect()
        else:
            self.stopSelect()

    def startSelect(self):
        """Start select mode."""
        if self._cid_mouse is None:
            canvas = self.plot_widget.canvas
            self._cid_mouse = canvas.mpl_connect('button_press_event', self.on_select)
            self._cid_key = canvas.mpl_connect('key_press_event', self.on_key)
            canvas.setFocus()
            self.plot_widget.captureMouse('INFO', 'element info', self.stopSelect)
        self.action.setChecked(True)

    def stopSelect(self):
        """Stop select mode."""
        if self._cid_mouse is not None:
            canvas = self.plot_widget.canvas
            canvas.mpl_disconnect(self._cid_mouse)
            canvas.mpl_disconnect(self._cid_key)
        self._cid_mouse = None
        self._cid_key = None
        self.action.setChecked(False)

    def on_select(self, event):
        """Display a popup window with info about the selected element."""
        if event.inaxes is None:
            return
        xpos = event.xdata * self.figure.unit['s']
        elem = self.segment.element_by_position(xpos)
        if elem is None or 'name' not in elem:
            return
        elem_name = elem['name']

        shift = bool(event.guiEvent.modifiers() & Qt.ShiftModifier)
        control = bool(event.guiEvent.modifiers() & Qt.ControlModifier)

        # By default, show info in an existing dialog. The shift/ctrl keys
        # are used to open more dialogs:
        if self._info_boxes and not shift and not control:
            box = self.activeBox()
            box.widget().el_name = elem_name
            box.setWindowTitle(elem_name)
            return

        dock, info = self.create_info_box(elem_name)
        notifyCloseEvent(dock, lambda: self._info_boxes.remove(dock))
        notifyEvent(info, 'focusInEvent', lambda event: self.setActiveBox(dock))

        frame = self.plot_widget.window()
        frame.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        if self._info_boxes and shift:
            frame.tabifyDockWidget(self.activeBox(), dock)
            dock.show()
            dock.raise_()

        self._info_boxes.append(dock)

        # Set focus to parent window, so left/right cursor buttons can be
        # used immediately.
        self.plot_widget.canvas.setFocus()

    def activeBox(self):
        return self._info_boxes[-1]

    def setActiveBox(self, box):
        self._info_boxes.remove(box)
        self._info_boxes.append(box)

    def create_info_box(self, elem_name):
        from madqt.widget.elementinfo import ElementInfoBox
        info = ElementInfoBox(self.segment, elem_name)
        dock = QtGui.QDockWidget()
        dock.setWidget(info)
        dock.setWindowTitle(elem_name)
        return dock, info

    def on_key(self, event):
        if not self._info_boxes:
            return
        if 'left' in event.key:
            move_step = -1
        elif 'right' in event.key:
            move_step = 1
        else:
            return
        cur_box = self.activeBox().widget()
        old_index = self.segment.get_element_index(cur_box.el_name)
        new_index = old_index + move_step
        elements = self.segment.elements
        new_elem = elements[new_index % len(elements)]
        cur_box.el_name = new_elem['name']
