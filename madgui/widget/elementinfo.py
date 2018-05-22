"""
Info boxes to display element detail.
"""

from collections import OrderedDict

from math import sqrt, pi, atan2
import itertools

import matplotlib as mpl
mpl.use('Qt5Agg')                       # select before mpl.backends import!
import matplotlib.backends.backend_qt5agg as mpl_backend
from matplotlib.patches import Ellipse

from madgui.qt import QtCore, QtGui
from madgui.core.base import Signal
from madgui.core.unit import ui_units, to_ui
from madgui.util.qt import fit_button
from madgui.util.layout import VBoxLayout, HBoxLayout
from madgui.widget.params import TabParamTables, ParamTable, CommandEdit


__all__ = [
    'ElementInfoBox',
]


class ElementInfoBox(QtGui.QWidget):

    changed_element = Signal()
    _el_id = None

    def __init__(self, model, el_id, **kwargs):
        super().__init__()

        self.notebook = TabParamTables([
            ('Summary', ParamTable(self._fetch_summary, self._update_element,
                                   model=model)),
            ('Params', CommandEdit(self._fetch_cmdpar, self._update_element,
                                   model=model)),
            ('Twiss', ParamTable(self._fetch_twiss)),
            ('Sigma', ParamTable(self._fetch_sigma)),
            ('Ellipse', EllipseWidget(model)),
            ('Sector', ParamTable(self._fetch_sector, units=False)),
        ])

        # navigation
        self.select = QtGui.QComboBox()
        self.select.addItems([elem.node_name for elem in model.elements])
        self.select.currentIndexChanged.connect(self.set_element)

        self.model = model
        self.el_id = el_id
        self.model.twiss.updated.connect(self.notebook.update)

        button_left = QtGui.QPushButton("<")
        button_right = QtGui.QPushButton(">")
        button_left.clicked.connect(lambda: self.advance(-1))
        button_right.clicked.connect(lambda: self.advance(+1))

        fit_button(button_left)
        fit_button(button_right)

        self.setLayout(VBoxLayout([
            HBoxLayout([button_left, self.select, button_right]),
            self.notebook,
        ], tight=True))


    def closeEvent(self, event):
        self.model.twiss.updated.disconnect(self.notebook.update)
        event.accept()

    def advance(self, step):
        elements  = self.model.elements
        old_index = self.model.get_element_index(self.el_id)
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
            self.select.setCurrentIndex(self.model.get_element_index(self.el_id))
            self.notebook.kw['elem_index'] = self.el_id
            self.notebook.update()
            self.changed_element.emit()

    @property
    def element(self):
        return self.model.elements[self.el_id]

    # for dialog.save/load:
    @property
    def exporter(self):
        return self.notebook.currentWidget().exporter

    def _fetch_cmdpar(self, elem_index):
        return list(self.model.sequence.expanded_elements[self.el_id]
                    .cmdpar.values())

    def _update_element(self, *args, **kwargs):
        return self.model.update_element(*args, **kwargs)

    #class BasicDataStore(ElementDataStore):
    def _fetch_summary(self, elem_index=0):
        elem = self.model.elements[elem_index]
        show = self.model.config['parameter_sets']['element']['show']
        data = OrderedDict([
            (k, getattr(elem, k))
            for k in show['common'] + show.get(elem.base_name, [])
        ])
        return self.model._par_list(data, 'element')

    def _fetch_twiss(self, elem_index=0):
        data = self.model.get_elem_twiss(elem_index)
        return self.model._par_list(data, 'twiss')

    def _fetch_sigma(self, elem_index=0):
        data = self.model.get_elem_sigma(elem_index)
        return self.model._par_list(data, 'sigma')

    def _fetch_sector(self, elem_index=0):
        sectormap = self.model.sectormap(elem_index)
        data = {
            'r{}{}'.format(i+1, j+1): sectormap[i,j]
            for i, j in itertools.product(range(6), range(6))
        }
        data.update({
            'k{}'.format(i+1): sectormap[6,i]
            for i in range(6)
        })
        return self.model._par_list(data, 'sector')


class EllipseWidget(QtGui.QWidget):

    def __init__(self, model):
        super().__init__()

        self.model = model
        self.figure = mpl.figure.Figure()
        self.canvas = canvas = mpl_backend.FigureCanvas(self.figure)
        self.toolbar = toolbar = mpl_backend.NavigationToolbar2QT(canvas, self)
        layout = VBoxLayout([canvas, toolbar])
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        # Needed on PyQt5 with tight_layout=True to prevent crash due to
        # singular matrix if size=0:
        canvas.setMinimumSize(QtCore.QSize(100, 100))
        canvas.resize(QtCore.QSize(100, 100))

    def update(self, elem_index):
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
