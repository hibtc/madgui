"""
Components to draw a 2D floor plan of a given MAD-X/Bmad lattice.
"""

# TODO: improve display of vertically oriented elements
# TODO: adjust display for custom entry/exit pole faces
# TODO: show scale indicator
# TODO: load styles from config
# TODO: rotate/place scene according to space requirements

from math import cos, sin, sqrt, pi

import numpy as np

from madqt.qt import Qt, QtCore, QtGui

__all__ = [
    'LatticeFloorPlan',
]


ELEMENT_COLOR = {
    'E_GUN':       'purple',
    'SBEND':       'red',
    'QUADRUPOLE':  'blue',
    'DRIFT':       'black',
    'LCAVITY':     'green',
    'RFCAVITY':    'green',
    'SEXTUPOLE':   'yellow',
    'WIGGLER':     'orange',
}

ELEMENT_WIDTH = {
    'E_GUN':       1.0,
    'LCAVITY':     0.4,
    'RFCAVITY':    0.4,
    'SBEND':       0.6,
    'QUADRUPOLE':  0.4,
    'SEXTUPOLE':   0.5,
    'DRIFT':       0.1,
}


def Rotation(theta, phi, psi, *, cos=cos, sin=sin):
    cy, sy = cos(theta), sin(theta)
    cx, sx = cos(phi),  -sin(phi)
    cz, sz = cos(psi),   sin(psi)
    def rotate(x, y, z):
        x, y = x*cz-y*sz, x*sz+y*cz
        y, z = y*cx-z*sx, y*sx+z*cx
        z, x = z*cy-x*sy, z*sy+x*cy
        return x, y, z
    return rotate


def Projection(ax1, ax2):
    ax1 = np.array(ax1) / np.dot(ax1, ax1)
    ax2 = np.array(ax2) / np.dot(ax2, ax2)
    return np.array([ax1, ax2]).dot


class Selector(QtGui.QWidget):

    def __init__(self, floorplan):
        super().__init__()
        self.floorplan = floorplan
        self.setLayout(QtGui.QHBoxLayout())
        self._addItem("Z|X", [ 0,  0,  1], [-1,  0,  0])
        self._addItem("X|Y", [-1,  0,  0], [ 0, -1,  0])
        self._addItem("Z|Y", [ 0,  0,  1], [ 0, -1,  0])

    def _addItem(self, label, *args):
        button = QtGui.QPushButton(label)
        button.clicked.connect(lambda: self.floorplan.setProjection(*args))
        self.layout().addWidget(button)


class LatticeFloorPlan(QtGui.QGraphicsView):

    """
    Graphics widget to draw 2D floor plan of given lattice.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setInteractive(True)
        self.setDragMode(QtGui.QGraphicsView.ScrollHandDrag)
        self.setBackgroundBrush(QtGui.QBrush(Qt.white, Qt.SolidPattern))
        self.setProjection([0, 0, 1], [-1, 0, 0])

    def setProjection(self, ax1, ax2):
        self.projection = Projection(ax1, ax2)
        if self.replay is not None:
            self.scene().clear()
            self.setElements(*self.replay)

    replay = None
    def setElements(self, utool, elements, survey, selection):
        self.replay = utool, elements, survey, selection
        self.setScene(QtGui.QGraphicsScene(self))
        for element, floor in zip(elements, survey):
            element = utool.dict_strip_unit(dict(element))
            self.scene().addItem(
                self.createElementGraphicsItem(element, floor, selection))
        self.setViewRect(self._sceneRect())
        selection.elements.update_after.connect(self._update_selection)

    def _sceneRect(self):
        rect = self.scene().sceneRect()
        return rect.marginsAdded(QtCore.QMarginsF(
            0.05*rect.width(), 0.05*rect.height(),
            0.05*rect.width(), 0.05*rect.height(),
        ))

    def resizeEvent(self, event):
        """Maintain visible region on resize."""
        self.setViewRect(self.view_rect)
        super().resizeEvent(event)

    def mapRectToScene(self, rect):
        """
        Map topleft/botright rect from viewport to scene coordinates.

        This assumes there is no rotation/shearing.
        """
        return QtCore.QRectF(
            self.mapToScene(rect.topLeft()),
            self.mapToScene(rect.bottomRight()))

    def setViewRect(self, rect):
        """
        Fit the given scene rectangle into the visible view.

        This assumes there is no rotation/shearing.
        """
        cur = self.mapRectToScene(self.viewport().rect())
        new = rect.intersected(self._sceneRect())
        self.zoom(min(cur.width()/new.width(),
                      cur.height()/new.height()))
        self.view_rect = new

    def zoom(self, scale):
        """Scale the figure uniformly along both axes."""
        self.scale(scale, scale)
        self.view_rect = self.mapRectToScene(self.viewport().rect())

    def wheelEvent(self, event):
        """Handle mouse wheel as zoom."""
        delta = event.angleDelta().y()
        self.zoom(1.0 + delta/1000.0)

    def _update_selection(self, slice, old_values, new_values):
        insert = set(new_values) - set(old_values)
        delete = set(old_values) - set(new_values)
        for item in self.scene().items():
            if item.el_id in insert:
                item.setSelected(True)
            if item.el_id in delete:
                item.setSelected(False)

    def createElementGraphicsItem(self, element, floor, selection):
        if element.get('type').lower() == 'multipole':
            angle = 0.0
        else:
            angle = float(element.get('angle', 0.0))
        if np.isclose(angle, 0.0):
            return StraightElementGraphicsItem(self, element, floor, selection)
        else:
            return CurvedElementGraphicsItem(self, element, floor, selection)


class ElementGraphicsItem(QtGui.QGraphicsItem):

    """Base class for element graphics items."""

    outline_pen = {'width': 1}
    orbit_pen = {'style': Qt.DashLine}
    select_pen = {'style': Qt.DashLine,
                  'color': 'green',
                  'width': 4}

    def __init__(self, plan, element, floor, selection):
        super().__init__()
        self.plan = plan
        self.floor = floor
        self.rotate = Rotation(floor.theta, floor.phi, floor.psi)
        self.element = element
        self.length = float(element.get('l', 0.0))
        self.angle = float(element.get('angle', 0.0))
        self.width = getElementWidth(element)
        self.color = getElementColor(element)
        self.walls = (0.5*self.width, 0.5*self.width) # inner/outer wall widths
        self.selection = selection
        self._outline = self.outline()
        self._orbit = self.orbit()

        self.setFlag(QtGui.QGraphicsItem.ItemIsSelectable, True)

        self.setSelected(self.el_id in selection.elements)

    @property
    def el_id(self):
        return self.element['el_id']

    def itemChange(self, change, value):
        if change == QtGui.QGraphicsItem.ItemSelectedHasChanged:
            self._on_select(value)
        return value

    def _on_select(self, select):
        is_selected = self.el_id in self.selection.elements
        if select and not is_selected:
            # TODO: incorporate whether shift is clicked
            self.selection.elements.append(self.el_id)
        elif is_selected and not select:
            self.selection.elements.remove(self.el_id)

    def shape(self):
        return self._outline

    def boundingRect(self):
        return self._outline.boundingRect()

    def paint(self, painter, option, widget):
        """Paint element + orbit + selection frame."""
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setBrush(Qt.NoBrush)
        # draw element outline:
        painter.setPen(createPen(**self.outline_pen))
        painter.fillPath(self._outline, self.color)
        painter.drawPath(self._outline)
        # draw beam orbit:
        painter.setPen(createPen(**self.orbit_pen))
        painter.drawPath(self._orbit)
        # highlight selected elements:
        if self.isSelected():
            painter.setPen(createPen(**self.select_pen))
            painter.drawPath(self._outline)

    # NOTE: drawing "backwards" because the origin (0,0) as at the exit face
    # of the element.

    def outline(self):
        """Return a QPainterPath that outlines the element."""
        raise NotImplementedError("abstract method")

    def orbit(self):
        """Return a QPainterPath that shows the beam orbit."""
        raise NotImplementedError("abstract method")

    def transform2D(self, x, y, z):
        f = self.floor
        x, y, z = self.rotate(x, y, z)
        x, y, z = x+f.x, y+f.y, z+f.z
        return self.plan.projection([x, y, z])


class StraightElementGraphicsItem(ElementGraphicsItem):

    def endpoints(self):
        return (self.transform2D(0, 0, -self.length),
                self.transform2D(0, 0, 0))

    def outline(self):
        r1, r2 = self.walls
        p0, p1 = self.endpoints()
        vect = p1-p0
        path = QtGui.QPainterPath()
        if not np.allclose(vect, 0):
            vect = vect / sqrt(np.dot(vect, vect))
            orth = np.array([-vect[1], vect[0]])
            path.moveTo(*(p0 - r2*orth))
            path.lineTo(*(p1 - r2*orth))
            path.lineTo(*(p1 + r1*orth))
            path.lineTo(*(p0 + r1*orth))
            path.closeSubpath()
        return path

    def orbit(self):
        a, b = self.endpoints()
        path = QtGui.QPainterPath()
        path.moveTo(*a)
        path.lineTo(*b)
        return path


class CurvedElementGraphicsItem(StraightElementGraphicsItem):

    def radius(self):
        return self.length / self.angle

    def endpoints(self):
        phi = self.angle
        rho = self.radius()
        c, s = cos(phi), sin(phi)
        return (self.transform2D(0, 0, 0),
                self.transform2D(c*rho-rho, 0, -s*rho))


def getElementColor(element, default='black'):
    return QtGui.QColor(ELEMENT_COLOR.get(element['type'].upper(), default))


def getElementWidth(element, default=0.2):
    return ELEMENT_WIDTH.get(element['type'].upper(), default)


def createPen(style=Qt.SolidLine, color='black', width=1):
    """
    Use this function to conveniently create a cosmetic pen with specified
    width. Integer widths create cosmetic pens (default) and float widths
    create scaling pens (this way you can set the figure style by changing a
    number).

    This is particularly important on PyQt5 where the default pen blacks out
    large areas of the figure if not being careful.
    """
    pen = QtGui.QPen(style)
    pen.setColor(QtGui.QColor(color))
    if isinstance(width, int):
        pen.setWidth(width)
        pen.setCosmetic(True)
    else:
        pen.setWidthF(width)
        pen.setCosmetic(False)
    return pen
