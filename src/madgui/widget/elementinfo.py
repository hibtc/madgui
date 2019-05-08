"""
Info boxes to display element detail.
"""

__all__ = [
    'ElementInfoBox',
    'EllipseWidget',
    'InfoBoxGroup',
]

from functools import partial

from math import sqrt, pi, atan2

from madgui.widget.plot import mpl_backend
from matplotlib.figure import Figure
from matplotlib.patches import Ellipse
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QComboBox, QToolButton, QWidget

from madgui.util.signal import Signal
from madgui.util.unit import ui_units, to_ui
from madgui.util.layout import VBoxLayout, HBoxLayout
from madgui.util.qt import EventFilter
from madgui.widget.dialog import Dialog
from madgui.widget.params import (
    TabParamTables, ParamTable, CommandEdit, ParamInfo, MatrixTable)


class ElementInfoBox(QWidget):

    changed_element = Signal()
    _el_id = None

    def __init__(self, model, el_id, summary, **kwargs):
        super().__init__()
        self.summary = summary

        self.notebook = TabParamTables([
            ('Summary', ParamTable(self._fetch_summary, self._update_element,
                                   model=model)),
            ('Params', CommandEdit(self._fetch_cmdpar, self._update_element,
                                   model=model)),
            ('Twiss', ParamTable(self._fetch_twiss)),
            ('Sigma', MatrixTable(self._fetch_sigma, shape=(6, 6),
                                  get_name=sigmat_title)),
            ('Ellipse', EllipseWidget(model)),
            ('Sector', MatrixTable(self._fetch_sector, shape=(6, 7),
                                   get_name=secmap_title, units=False)),
        ])

        # navigation
        self.select = QComboBox()
        self.select.addItems([elem.node_name for elem in model.elements])
        self.select.currentIndexChanged.connect(self.set_element)

        self.model = model
        self.el_id = el_id
        self.model.updated.connect(self.notebook.update)

        button_left = QToolButton()
        button_right = QToolButton()
        button_left.clicked.connect(lambda: self.advance(-1))
        button_right.clicked.connect(lambda: self.advance(+1))

        button_left.setArrowType(Qt.LeftArrow)
        button_right.setArrowType(Qt.RightArrow)

        self.setLayout(VBoxLayout([
            HBoxLayout([button_left, self.select, button_right]),
            self.notebook,
        ], tight=True))

    def closeEvent(self, event):
        self.model.updated.disconnect(self.notebook.update)
        super().closeEvent(event)

    def advance(self, step):
        elements = self.model.elements
        old_index = elements.index(self.el_id)
        new_index = old_index + step
        new_el_id = elements[new_index % len(elements)].index
        self.el_id = new_el_id

    @property
    def el_id(self):
        return self._el_id

    @el_id.setter
    def el_id(self, name):
        self.set_element(name)

    def set_element(self, name):
        if name != self._el_id:
            self._el_id = name
            self.select.setCurrentIndex(self.model.elements.index(self.el_id))
            self.notebook.kw['elem_index'] = self.el_id
            self.notebook.update()
            self.window().setWindowTitle(
                "Element details: " + self.model.elements[self.el_id].node_name)
            self.changed_element.emit()

    @property
    def element(self):
        return self.model.elements[self.el_id]

    # for dialog.save/load:
    @property
    def exporter(self):
        return self.notebook.currentWidget().exporter

    def _fetch_cmdpar(self, elem_index):
        elem = self.model.sequence.expanded_elements[elem_index]
        cmdpars = list(elem.cmdpar.values())
        # Implicit drifts being shallow clones of the base DRIFT have inform=1
        # for all attributes (even those that are unchanged from a base drift).
        # This results in everything being shown in bold style, which is ugly.
        # We suppress it by setting inform=0 for most attributes:
        if getattr(elem, 'occ_cnt', None) == 0:
            for par in cmdpars:
                par.inform = par.name in ('at', 'l')
        return cmdpars

    def _update_element(self, *args, **kwargs):
        return self.model.update_element(*args, **kwargs)

    def _fetch_summary(self, elem_index=0):
        elem = self.model.elements[elem_index]
        show = self.summary
        data = {
            k: getattr(elem, k)
            for k in show['common'] + show.get(elem.base_name, [])
        }
        return [ParamInfo(k.title(), v, mutable=k in elem)
                for k, v in data.items()]

    def _fetch_twiss(self, elem_index=0):
        data = self.model.get_elem_twiss(elem_index)
        return [ParamInfo(k.title(), v) for k, v in data.items()]

    def _fetch_sigma(self, elem_index=0):
        return self.model.get_elem_sigma(elem_index)

    def _fetch_sector(self, elem_index=0):
        return self.model.sectormap(elem_index)


def sigmat_title(i, j):
    return 'Sig{}{}'.format(i, j)


def secmap_title(i, j):
    return ('R{}{}' if j < 7 else 'K{}').format(i, j)


class EllipseWidget(QWidget):

    def __init__(self, model):
        super().__init__()

        self.model = model
        self.figure = Figure()
        self.canvas = canvas = mpl_backend.FigureCanvas(self.figure)
        self.toolbar = toolbar = mpl_backend.NavigationToolbar2QT(canvas, self)
        self.setLayout(VBoxLayout([canvas, toolbar], tight=True))
        # Needed on PyQt5 with tight_layout=True to prevent crash due to
        # singular matrix if size=0:
        canvas.setMinimumSize(QSize(100, 100))
        canvas.resize(QSize(100, 100))

    def update(self, elem_index=0):
        self.figure.clf()
        axx = self.figure.add_subplot(121)
        axy = self.figure.add_subplot(122)

        def ellipse(ax, alfa, beta, gamma, eps):
            phi = atan2(2*alfa, gamma-beta) / 2

            # See: ELLIPTICAL TRANSFORMATIONS FOR BEAM OPTICS, R.B. Moore, 2004
            # http://www.physics.mcgill.ca/~moore/Notes/Ellipses.pdf
            H = (beta + gamma) / 2
            w = sqrt(eps/2) * (sqrt(H+1) - sqrt(H-1))
            h = sqrt(eps/2) * (sqrt(H+1) + sqrt(H-1))

            # Same as:
            # c, s = cos(phi), sin(phi)
            # R = np.array([[c, -s], [s, c]])
            # M = np.array([[beta, -alfa], [-alfa, gamma]])
            # T = R.T.dot(M).dot(R)
            # w = sqrt(eps*T[0,0])
            # h = sqrt(eps*T[1,1])

            dx = sqrt(eps*beta)
            dy = sqrt(eps*gamma)
            ax.set_xlim(-dx*1.2, dx*1.2)
            ax.set_ylim(-dy*1.2, dy*1.2)

            # zorder needed to draw on top of grid:
            ax.add_patch(Ellipse((0, 0), 2*w, 2*h, phi/pi*180,
                                 fill=False, zorder=5))
            ax.grid(True)

        # FIXME: gui_units
        twiss = to_ui(self.model.get_elem_twiss(elem_index))
        ellipse(axx, twiss.alfx, twiss.betx, twiss.gamx, twiss.ex)
        ellipse(axy, twiss.alfy, twiss.bety, twiss.gamy, twiss.ey)

        axx.set_xlabel("x [{}]".format(ui_units.label('x')))
        axy.set_xlabel("y [{}]".format(ui_units.label('y')))
        axx.set_ylabel("px | py")

        self.figure.tight_layout()
        self.canvas.draw()


class InfoBoxGroup:

    def __init__(self, mainwindow, selection):
        """Add toolbar tool to panel and subscribe to capture events."""
        self.mainwindow = mainwindow
        self.model = mainwindow.model
        self.selection = selection
        self.boxes = [self.create_info_box(elem) for elem in selection]
        selection.inserted.connect(self._insert)
        selection.removed.connect(self._delete)
        selection.changed.connect(self._modify)
        selection.cursor.changed.connect(self._cursor_changed)
        self.event_filter = EventFilter({
            'WindowActivate': self._on_activate_box,
            'Close': self._on_close_box,
        })

    # keep info boxes in sync with current selection

    def _insert(self, index, el_id):
        self.boxes.insert(index, self.create_info_box(el_id))

    def _delete(self, index):
        if self.boxes[index].isVisible():
            self.boxes[index]._el_id = None
            self.boxes[index].window().close()
        del self.boxes[index]

    def _modify(self, index, el_id):
        self.boxes[index].el_id = el_id

    def _cursor_changed(self, index):
        self.boxes[index].window().present()

    # utility methods

    def _on_close_box(self, window, *_):
        window.removeEventFilter(self.event_filter)
        box = window.widget()
        if box.el_id is not None:
            self.selection.remove(box.el_id)

    def _on_activate_box(self, window, *_):
        box = window.widget()
        self.selection.cursor.set(self.boxes.index(box), force=True)

    def create_info_box(self, el_id):
        model = self.model()
        config = self.mainwindow.config
        info = ElementInfoBox(model, el_id, config.summary_attrs)
        info.changed_element.connect(partial(self._changed_box_element, info))
        dock = Dialog(self.mainwindow)
        dock.setSimpleExportWidget(info, None)
        dock.installEventFilter(self.event_filter)
        dock.present()
        return info

    def _changed_box_element(self, box):
        self.selection.cursor.set(self.boxes.index(box))
        self.selection.add(box.el_id, replace=True)
