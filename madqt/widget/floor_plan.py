# encoding: utf-8
"""
Components to draw a 2D floor plan of a given MAD-X/Bmad lattice.
"""

# TODO: show element info box on selection
# TODO: improve display of elements with vertical angles
# TODO: adjust display for custom entry/exit pole faces

from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import division

import math

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


def createElementGraphicsItem(element):
    angle = float(element.get('angle', 0.0))
    if angle == 0.0:
        return StraightElementGraphicsItem(element)
    else:
        return CurvedElementGraphicsItem(element)


class ElementGraphicsItem(QtGui.QGraphicsItem):

    """Base class for element graphics items."""

    outline_pen = {'width': 1}
    orbit_pen = {'style': Qt.DashLine}
    select_pen = {'style': Qt.DashLine,
                  'color': 'green',
                  'width': 4}

    def __init__(self, element):
        super(ElementGraphicsItem, self).__init__()
        self.element = element
        self.length = float(element.get('l', 0.0))
        self.angle = float(element.get('angle', 0.0))
        self.width = getElementWidth(element)
        self.color = getElementColor(element)
        self.walls = (0.5*self.width, 0.5*self.width) # inner/outer wall widths
        self._outline = self.outline()
        self._orbit = self.orbit()

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


class LatticeFloorPlan(QtGui.QGraphicsView):

    """
    Graphics widget to draw 2D floor plan of given lattice.
    """

    def __init__(self, *args, **kwargs):
        super(LatticeFloorPlan, self).__init__(*args, **kwargs)
        self.setInteractive(True)
        self.setDragMode(QtGui.QGraphicsView.ScrollHandDrag)
        self.setBackgroundBrush(QtGui.QBrush(Qt.white, Qt.SolidPattern))

    def setElements(self, elements, survey):
        self.setScene(QtGui.QGraphicsScene(self))
        for element, floor in zip(elements, survey):
            item = createElementGraphicsItem(element)
            item.setFlag(QtGui.QGraphicsItem.ItemIsSelectable, True)
            item.setPos(floor.z, -floor.x)
            item.setRotation(-rad2deg(floor.theta))
            self.scene().addItem(item)
        self.setViewRect(self.scene().sceneRect())

    def resizeEvent(self, event):
        """Maintain visible region on resize."""
        new, old = event.size(), event.oldSize()
        if not old.isEmpty():
            self.setViewRect(self.mapRectToScene(self.canvas_rect))
        self.canvas_rect = self.viewport().rect()
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

    def zoom(self, scale):
        """Scale the figure uniformly along both axes."""
        self.scale(scale, scale)

    def wheelEvent(self, event):
        """Handle mouse wheel as zoom."""
        try:
            delta = event.delta()               # PyQt4
        except AttributeError:
            delta = event.angleDelta().y()      # PyQt5
        self.zoom(1.0 + delta/1000.0)
