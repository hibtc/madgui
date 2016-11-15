# encoding: utf-8
"""
Components to draw a 2D floor plan of a given MAD-X/Bmad lattice.
"""

# TODO: improve display of vertically oriented elements
# TODO: adjust display for custom entry/exit pole faces
# TODO: show scale indicator
# TODO: load styles from config
# TODO: rotate/place scene according to space requirements

from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import division

import math

from numpy import isclose

from six import integer_types

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


class LatticeFloorPlan(QtGui.QGraphicsView):

    """
    Graphics widget to draw 2D floor plan of given lattice.
    """

    def __init__(self, *args, **kwargs):
        super(LatticeFloorPlan, self).__init__(*args, **kwargs)
        self.setInteractive(True)
        self.setDragMode(QtGui.QGraphicsView.ScrollHandDrag)
        self.setBackgroundBrush(QtGui.QBrush(Qt.white, Qt.SolidPattern))

    def setElements(self, utool, elements, survey, selection):
        self.setScene(QtGui.QGraphicsScene(self))
        for element, floor in zip(elements, survey):
            element = utool.dict_strip_unit(element)
            self.scene().addItem(
                createElementGraphicsItem(element, floor, selection))
        self.setViewRect(self.scene().sceneRect())
        selection.elements.update_after.connect(self._update_selection)

    def resizeEvent(self, event):
        """Maintain visible region on resize."""
        self.setViewRect(self.view_rect)
        super(LatticeFloorPlan, self).resizeEvent(event)

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
        new = rect.intersected(self.scene().sceneRect())
        self.zoom(min(cur.width()/new.width(),
                      cur.height()/new.height()))
        self.view_rect = new

    def zoom(self, scale):
        """Scale the figure uniformly along both axes."""
        self.scale(scale, scale)
        self.view_rect = self.mapRectToScene(self.viewport().rect())

    def wheelEvent(self, event):
        """Handle mouse wheel as zoom."""
        try:
            delta = event.delta()               # PyQt4
        except AttributeError:
            delta = event.angleDelta().y()      # PyQt5
        self.zoom(1.0 + delta/1000.0)

    def _update_selection(self, slice, old_values, new_values):
        insert = set(new_values) - set(old_values)
        delete = set(old_values) - set(new_values)
        for item in self.scene().items():
            if item.el_name in insert:
                item.setSelected(True)
            if item.el_name in delete:
                item.setSelected(False)


def createElementGraphicsItem(element, floor, selection):
    angle = float(element.get('angle', 0.0))
    if isclose(angle, 0.0):
        return StraightElementGraphicsItem(element, floor, selection)
    else:
        return CurvedElementGraphicsItem(element, floor, selection)


class ElementGraphicsItem(QtGui.QGraphicsItem):

    """Base class for element graphics items."""

    outline_pen = {'width': 1}
    orbit_pen = {'style': Qt.DashLine}
    select_pen = {'style': Qt.DashLine,
                  'color': 'green',
                  'width': 4}

    def __init__(self, element, floor, selection):
        super(ElementGraphicsItem, self).__init__()
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
        self.setPos(floor.z, -floor.x)
        self.setRotation(-rad2deg(floor.theta))

        self.setSelected(self.el_name in selection.elements)

    @property
    def el_name(self):
        return self.element['name']

    def itemChange(self, change, value):
        if change == QtGui.QGraphicsItem.ItemSelectedHasChanged:
            self._on_select(value)
        return value

    def _on_select(self, select):
        is_selected = self.el_name in self.selection.elements
        if select and not is_selected:
            # TODO: incorporate whether shift is clicked
            self.selection.elements.append(self.el_name)
        elif is_selected and not select:
            self.selection.elements.remove(self.el_name)

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


class StraightElementGraphicsItem(ElementGraphicsItem):

    def outline(self):
        path = QtGui.QPainterPath()
        r1, r2 = self.walls
        w = self.length
        path.moveTo(0, 0)
        path.lineTo(0, -r2)
        path.lineTo(-w, -r2)
        path.lineTo(-w,  r1)
        path.lineTo(0, r1)
        path.lineTo(0, 0)
        return path

    def orbit(self):
        path = QtGui.QPainterPath()
        path.lineTo(-self.length, 0)
        return path


class CurvedElementGraphicsItem(ElementGraphicsItem):

    def radius(self):
        return self.length / self.angle

    def outline(self):
        angle = self.angle
        rho = self.radius()
        deg = rad2deg(angle)
        cos = math.cos(angle)
        sin = math.sin(angle)
        w1, w2 = self.walls         # inner/outer wall widths
        r1, r2 = rho-w1, rho+w2     # inner/outer wall radius
        path = QtGui.QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(0, w1)
        path.arcTo(-r1, w1, 2*r1, 2*r1, 90, deg)
        path.lineTo(-r2*sin, rho-cos*r2)
        path.arcTo(-r2, -w2, 2*r2, 2*r2, 90+deg, -deg)
        path.lineTo(0, 0)
        return path

    def orbit(self):
        rho = self.radius()
        deg = rad2deg(self.angle)
        path = QtGui.QPainterPath()
        path.arcTo(-rho, 0, 2*rho, 2*rho, 90, deg)
        return path


def rad2deg(rad):
    return rad * (180/math.pi)


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
    if isinstance(width, integer_types):
        pen.setWidth(width)
        pen.setCosmetic(True)
    else:
        pen.setWidthF(width)
        pen.setCosmetic(False)
    return pen
