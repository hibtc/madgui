# encoding: utf-8
"""
Components to draw a 2D floor plan of a given MAD-X/Bmad lattice.
"""

# TODO: show element info box on selection
# TODO: improve display of elements with vertical angles

from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import division

from six import integer_types

from madqt.qt import Qt, QtCore, QtGui

import math


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


def getElementColor(ele, default='black'):
    return QtGui.QColor(ELEMENT_COLOR.get(ele['type'].upper(), default))


def getElementWidth(ele, default=0.2):
    return ELEMENT_WIDTH.get(ele['type'].upper(), default)


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


class EleGraphicsItem(QtGui.QGraphicsItem):

    outline_pen = {'width': 1}
    orbit_pen = {'style': Qt.DashLine}
    select_pen = {'style': Qt.DashLine,
                  'color': 'green',
                  'width': self.select_width}

    def __init__(self, ele, scale=1):
        super(EleGraphicsItem, self).__init__()
        self.setAcceptHoverEvents(True)
        self.name = ele['name']
        self.ele = ele
        self._r1 = 0.5*getElementWidth(self.ele) # Inner wall width
        self._r2 = 0.5*getElementWidth(self.ele) # Outer wall width
        self._angle = float(ele.get('angle', 0.0))
        self._length = float(ele['l'])
        self._width = self._r1+self._r2
        self._shape = self._EleShape()

    def _EleShape(self):
        """ returns a QPainterPath that outlines the ele """
        path = QtGui.QPainterPath()
        angle = self._angle
        length = self._length
        r1 = self._r1
        r2 = self._r2
        if angle != 0.0:
            # Curved Geometry
            rho = length/angle
            st = math.sin(angle)
            ct = math.cos(angle)
            path.moveTo(0, 0)
            path.lineTo(0, r1)
            path.arcTo(-rho+r1, r1, 2*(rho-r1), 2*(rho-r1), 90.0, angle*180.0/math.pi)
            path.lineTo(-(rho+r2)*st, rho-ct*(rho+r2))
            path.arcTo(-rho-r2,-r2, 2*(rho+r2), 2*(rho+r2), 90.0+angle*180.0/math.pi, -angle*180.0/math.pi)
            path.lineTo(0, 0)
            if angle > 0:
                w = (r2+rho)*st
                h = r2 + rho*(1-ct) + r1*ct
                self._boundingRect = QtCore.QRectF(-1.05*w,-1.05*r2, 1.1*w, 1.1*h)
            else:
                w = (rho-r1)*st
                h = r1 + r2*ct - rho*(1-ct)
                self._boundingRect = QtCore.QRectF(-1.05*w, 1.05*(-h+r1), 1.1*w, 1.1*h)

        else:
            # Straight Geometry
            w = self._length
            h = self._width
            self._boundingRect = QtCore.QRectF(-1.05*w, -1.1*r2, 1.1*w, 1.1*h)
            path.moveTo(0, 0)
            path.lineTo(0, -r2)
            path.lineTo(-w, -r2)
            path.lineTo(-w,  r1)
            path.lineTo(0, r1)
            path.lineTo(0, 0)
        return path

    def boundingRect(self):
        return  self._boundingRect

    def hoverEnterEvent(self, event):
        pass

    def paint(self, painter, option, widget):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setBrush(Qt.NoBrush)

        # Draw and fill shape
        painter.setPen(createPen(**self.outline_pen))
        painter.fillPath(self._shape, getElementColor(self.ele))
        painter.drawPath(self._shape)

        # Reference Orbit for curved and straight geometries
        painter.setPen(createPen(**self.orbit_pen))
        if self._angle != 0.0:
            rho = self._length/self._angle
            path = QtGui.QPainterPath()
            path.arcTo(-rho, 0, 2*rho, 2*rho, 90, self._angle*180/math.pi)
            painter.drawPath(path)

        else:
            line = QtCore.QLineF(-self._length, 0, 0, 0)
            painter.drawLine(line)

        # isSelected highlighting
        if self.isSelected():
            painter.setPen(createPen(**self.select_pen)))
            painter.drawPath(self._shape)

    def shape(self):
        return self._shape


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
        for ele, floor in zip(elements, survey):
            item = EleGraphicsItem(ele)
            item.setFlag(QtGui.QGraphicsItem.ItemIsSelectable, True)
            item.setPos(floor.z, -floor.x)
            item.setRotation(-floor.theta*180/math.pi)
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
