"""
Components to draw a 2D floor plan of a given MAD-X lattice.
"""

# TODO: improve display of vertically oriented elements
# TODO: adjust display for custom entry/exit pole faces
# TODO: load styles from config
# TODO: rotate/place scene according to space requirements

__all__ = [
    'FloorCoords',
    'FloorPlanWidget',
    'LatticeFloorPlan',
]

from collections import namedtuple
from math import cos, sin, sqrt, pi, atan2, floor, log10

import numpy as np
from PyQt5.QtCore import QMarginsF, QPointF, QRectF, Qt
from PyQt5.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath,
    QPen, QPolygonF)
from PyQt5.QtWidgets import (
    QGraphicsItem, QGraphicsScene, QGraphicsView,
    QPushButton, QWidget)

from madgui.util.layout import VBoxLayout


FloorCoords = namedtuple('FloorCoords', ['x', 'y', 'z', 'theta', 'phi', 'psi'])


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

rot90 = np.array([[0, -1], [1, 0]])


def Rotation2(phi):
    c, s = cos(phi), sin(phi)
    return lambda x, y: (c*x - s*y, c*y + s*x)


def Rotation3(theta, phi, psi, *, Rotation2=Rotation2):
    ry = Rotation2(theta)
    rx = Rotation2(-phi)
    rz = Rotation2(psi)

    def rotate(x, y, z):
        x, y = rz(x, y)
        y, z = rx(y, z)
        z, x = ry(z, x)
        return x, y, z
    return rotate


def Projection(ax1, ax2):
    ax1 = np.array(ax1) / np.dot(ax1, ax1)
    ax2 = np.array(ax2) / np.dot(ax2, ax2)
    return np.array([ax1, ax2])


def normalize(vec):
    if np.allclose(vec, 0):
        return np.zeros(2)
    return vec / sqrt(np.dot(vec, vec))


class FloorPlanWidget(QWidget):

    def __init__(self, session):
        super().__init__()
        self.setWindowTitle("2D floor plan")
        self.floorplan = LatticeFloorPlan()
        self.floorplan.set_session(session)
        self.setLayout(VBoxLayout([
            self.floorplan, [
                self._button("Z|X", -pi/2, pi/2),
                self._button("X|Y",     0,    0),
                self._button("Z|Y", -pi/2,    0),
            ],
        ]))

    def _button(self, label, *args):
        button = QPushButton(label)
        button.clicked.connect(lambda: self.floorplan.setProjection(*args))
        return button


class LatticeFloorPlan(QGraphicsView):

    """
    Graphics widget to draw 2D floor plan of given lattice.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setInteractive(True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setBackgroundBrush(QBrush(Qt.white, Qt.SolidPattern))
        self.setProjection(-pi/2, pi/2)
        self.selection = set()

    def setProjection(self, theta, phi, psi=0):
        phi = np.clip(phi, -pi/8, pi/2)
        rot = Rotation3(theta, phi, psi)
        ax1 = np.array(list(rot(1, 0, 0)))
        ax2 = np.array(list(rot(0, 1, 0)))
        self.theta, self.phi, self.psi = theta, phi, psi
        self.projection = Projection(ax1, -ax2)
        if self.replay is not None:
            self.scene().clear()
            self.setElements(*self.replay)

    session = None
    model = None

    def set_session(self, session):
        self.selection = session.selected_elements
        self.session = session
        self.session.model.changed.connect(self.set_model)
        self.set_model(session.model())

    def set_model(self, model):
        # TODO: only update when SBEND/MULTIPOLE/SROTATION etc changes?
        if self.model:
            self.model.updated.disconnect(self._updateSurvey)
        self.model = model
        if model:
            self.model.updated.connect(self._updateSurvey)
            self._updateSurvey()

    def _updateSurvey(self):
        survey = self.model.survey()
        array = np.array([survey[key] for key in FloorCoords._fields])
        floor = [FloorCoords(*row) for row in array.T]
        self.setElements(self.model.elements, floor, self.selection)

    replay = None

    def setElements(self, elements, survey, selection):
        self.replay = elements, survey, selection
        self.setScene(QGraphicsScene(self))
        survey = [FloorCoords(0, 0, 0, 0, 0, 0)] + survey
        for element, coords in zip(elements, zip(survey, survey[1:])):
            self.scene().addItem(
                ElementGraphicsItem(self, element, coords, selection))
        self.coordinate_axes = CoordinateAxes(self)
        self.scale_indicator = ScaleIndicator(self)
        self.scene().addItem(self.coordinate_axes)
        self.scene().addItem(self.scale_indicator)
        self.setViewRect(self._sceneRect())
        if hasattr(selection, 'update_finished'):
            selection.update_finished.connect(self._update_selection)

    def _sceneRect(self):
        rect = self.scene().sceneRect()
        return rect.marginsAdded(QMarginsF(
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
        return QRectF(
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
        self.coordinate_axes.update()
        self.scale_indicator.update()

    def zoom(self, scale):
        """Scale the figure uniformly along both axes."""
        self.scale(scale, scale)
        self.view_rect = self.mapRectToScene(self.viewport().rect())

    def wheelEvent(self, event):
        """Handle mouse wheel as zoom."""
        delta = event.angleDelta().y()
        self.zoom(1.0 + delta/1000.0)

    def mousePressEvent(self, event):
        self.last_mouse_position = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.RightButton:
            delta = event.pos() - self.last_mouse_position
            theta = self.theta + delta.x()/100
            phi = self.phi + delta.y()/100
            self.setProjection(theta, phi)
            self.last_mouse_position = event.pos()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _update_selection(self, slice, old_values, new_values):
        insert = set(new_values) - set(old_values)
        delete = set(old_values) - set(new_values)
        for item in self.scene().items():
            if item.el_id in insert:
                item.setSelected(True)
            if item.el_id in delete:
                item.setSelected(False)


class ElementGraphicsItem(QGraphicsItem):

    """Base class for element graphics items."""

    outline_pen = {'width': 1}
    orbit_pen = {'style': Qt.DashLine}
    select_pen = {'style': Qt.DashLine,
                  'color': 'green',
                  'width': 4}

    def __init__(self, plan, element, coords, selection):
        super().__init__()
        self.plan = plan
        self.coords = coords
        self.rotate = (Rotation3(coords[0].theta, coords[0].phi, coords[0].psi),
                       Rotation3(coords[1].theta, coords[1].phi, coords[1].psi))
        self.element = element
        self.length = element.length
        self.angle = float(element.get('angle', 0.0))
        self.width = getElementWidth(element)
        self.color = getElementColor(element)
        self.walls = (0.5*self.width, 0.5*self.width)   # inner/outer wall widths
        self.selection = selection
        self._outline = self.outline()
        self._orbit = self.orbit()

        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

        self.setSelected(self.el_id in selection)

    @property
    def el_id(self):
        return self.element.index

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self._on_select(value)
        return value

    def _on_select(self, select):
        is_selected = self.el_id in self.selection
        if select and not is_selected:
            # TODO: incorporate whether shift is clicked
            self.selection.add(self.el_id)
        elif is_selected and not select:
            self.selection.remove(self.el_id)

    def shape(self):
        return self._outline

    def boundingRect(self):
        return self._outline.boundingRect()

    def paint(self, painter, option, widget):
        """Paint element + orbit + selection frame."""
        painter.setRenderHint(QPainter.Antialiasing)
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

    def endpoints(self):
        proj2D = self.plan.projection.dot
        p0, p1 = self.coords
        return (proj2D([p0.x, p0.y, p0.z]),
                proj2D([p1.x, p1.y, p1.z]))

    def outline(self):
        """Return a QPainterPath that outlines the element."""
        r1, r2 = self.walls
        p0, p1 = self.endpoints()
        proj2D = self.plan.projection.dot
        vec0 = normalize(np.dot(rot90, proj2D(list(self.rotate[0](0, 0, 1)))))
        vec1 = normalize(np.dot(rot90, proj2D(list(self.rotate[1](0, 0, 1)))))
        path = QPainterPath()
        path.moveTo(*(p0 - r2*vec0))
        path.lineTo(*(p1 - r2*vec1))
        path.lineTo(*(p1 + r1*vec1))
        path.lineTo(*(p0 + r1*vec0))
        path.closeSubpath()
        return path

    def orbit(self):
        """Return a QPainterPath that shows the beam orbit."""
        a, b = self.endpoints()
        path = QPainterPath()
        path.moveTo(*a)
        path.lineTo(*b)
        return path


def getElementColor(element, default='black'):
    return QColor(ELEMENT_COLOR.get(element.base_name.upper(), default))


def getElementWidth(element, default=0.2):
    return ELEMENT_WIDTH.get(element.base_name.upper(), default)


def createPen(style=Qt.SolidLine, color='black', width=1):
    """
    Use this function to conveniently create a cosmetic pen with specified
    width. Integer widths create cosmetic pens (default) and float widths
    create scaling pens (this way you can set the figure style by changing a
    number).

    This is particularly important on PyQt5 where the default pen blacks out
    large areas of the figure if not being careful.
    """
    pen = QPen(style)
    pen.setColor(QColor(color))
    if isinstance(width, int):
        pen.setWidth(width)
        pen.setCosmetic(True)
    else:
        pen.setWidthF(width)
        pen.setCosmetic(False)
    return pen


class CoordinateAxes(QGraphicsItem):

    """Display axes of coordinates."""

    el_id = None
    pen = {'style': Qt.SolidLine,
           'color': 'orange',
           'width': 1}

    def __init__(self, plan):
        super().__init__()
        self.plan = plan
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)

    def update(self):
        self._path = self.draw_path()

    def shape(self):
        return self._path

    def boundingRect(self):
        # Ignore this item when calculating the scene rect:
        return QRectF()

    def paint(self, painter, option, widget):
        pen = createPen(**self.pen)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(pen)
        painter.setBrush(QBrush(pen.color(), Qt.SolidPattern))
        painter.drawPath(self._path)

    def draw_path(self):
        l, s, d = 45, 10, 10
        proj = self.plan.projection.dot
        orig = np.array([0, 0])
        axes = QPainterPath()
        axes.addPath(self.axis_arrow("x", orig, orig+l*proj([1, 0, 0]), s))
        axes.addPath(self.axis_arrow("y", orig, orig+l*proj([0, 1, 0]), s))
        axes.addPath(self.axis_arrow("z", orig, orig+l*proj([0, 0, 1]), s))

        tran = self.deviceTransform(self.plan.viewportTransform()).inverted()[0]
        view = tran.mapRect(QRectF(self.plan.viewport().rect()))
        rect = axes.boundingRect()
        axes.translate(view.left() + view.width()/15 - rect.left(),
                       view.bottom() - view.height()/15 - rect.bottom())
        path = QPainterPath()
        path.addPath(axes)
        path.addEllipse(-d/2, -d/2, d, d)
        return path

    def axis_arrow(self, label, x0, x1, arrow_size):
        path = arrow(x0, x1, arrow_size)
        if not path:
            return QPainterPath()
        plan = self.plan
        font = QFont(plan.font())
        font.setPointSize(14)
        metr = QFontMetrics(font)
        rect = metr.boundingRect(label)
        rect.setHeight(metr.xHeight())
        tran = self.deviceTransform(self.plan.viewportTransform()).inverted()[0]
        size = tran.mapRect(QRectF(rect)).size()
        w, h = size.width(), size.height()
        dir_ = (x1 - x0) / np.linalg.norm(x1 - x0)
        offs = [-w/2, +h/2] + dir_ * max(w, h)
        path.addText(QPointF(*(x1 + offs)), font, label)
        return path


def arrow(x0, x1, arrow_size=0.3, arrow_angle=pi/5):
    dx, dy = x1 - x0
    if dy**2 + dx**2 < arrow_size**2:
        return None
    path = QPainterPath()
    path.moveTo(*x0)
    path.lineTo(*x1)
    angle = atan2(dy, dx)
    p1 = x1 + [cos(angle + pi + arrow_angle) * arrow_size,
               sin(angle + pi + arrow_angle) * arrow_size]
    p2 = x1 + [cos(angle + pi - arrow_angle) * arrow_size,
               sin(angle + pi - arrow_angle) * arrow_size]
    path.addPolygon(QPolygonF([
        QPointF(*x1),
        QPointF(*p1),
        QPointF(*p2),
        QPointF(*x1),
    ]))
    return path


class ScaleIndicator(QGraphicsItem):

    """Display small scale indicator."""

    el_id = None
    pen = {'style': Qt.SolidLine,
           'color': 'orange',
           'width': 2}

    def __init__(self, plan):
        super().__init__()
        self.plan = plan
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)

    def update(self):
        self._path = self.draw_path()

    def shape(self):
        return self._path

    def boundingRect(self):
        # Ignore this item when calculating the scene rect:
        return QRectF()

    def paint(self, painter, option, widget):
        pen = createPen(**self.pen)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self._path)

    def draw_path(self):
        plan = self.plan
        rect = plan.mapRectToScene(plan.viewport().rect())
        rect.setWidth(10**floor(log10(rect.width()/2)))
        text = "{} m".format(round(rect.width()))

        tran = self.deviceTransform(plan.viewportTransform()).inverted()[0]
        width = tran.mapRect(QRectF(
            plan.mapFromScene(rect.topLeft()),
            plan.mapFromScene(rect.bottomRight()))).width()

        view = tran.mapRect(plan.viewport().rect())
        x0 = QPointF(view.right() - view.width()/15,
                     view.bottom() - view.height()/15)
        x1 = x0 - QPointF(width, 0)

        head = QPointF(0, 8)
        path = QPainterPath()
        path.moveTo(x0)
        path.lineTo(x1)
        path.moveTo(x0 + head)
        path.lineTo(x0 - head)
        path.moveTo(x1 + head)
        path.lineTo(x1 - head)

        # add label
        font = QFont(plan.font())
        font.setPointSize(14)
        rect = QFontMetrics(font).boundingRect(text)
        size = tran.mapRect(QRectF(rect)).size()
        w, h = size.width(), size.height()
        offs = [-w/2, -h/2]
        path.addText((x0+x1)/2 + QPointF(*offs), font, text)
        return path
