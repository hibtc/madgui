"""
Components to draw a 3D floor plan of a given MAD-X lattice.
"""

# TODO: entry/exit pole faces
# TODO: load styles from config + UI
# TODO: add exporters for common 3D data formats (obj+mtl/collada/ply?)
# TODO: customize settings via UI (wireframe etc)
# TODO: show thin elements as disks (kicker/monitor)

__all__ = [
    'LatticeFloorPlan',
]

from collections import namedtuple
from math import pi

import numpy as np
from PyQt5.QtCore import Qt, QSize, QTimer, QTime
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget, QPushButton, QOpenGLWidget

from madgui.util.layout import VBoxLayout

import OpenGL.GL as GL

from .transform import gl_array, rotate, translate
from .camera import Camera
from .shapes import cylinder, torus_arc
from .gl_util import (
    load_shader, create_shader_program, Object3D,
    set_uniform_matrix, set_uniform_vector)


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


class FloorPlanWidget(QWidget):

    def __init__(self, session):
        super().__init__()
        self.setWindowTitle("3D floor plan")
        self.floorplan = LatticeFloorPlan()
        self.floorplan.camera_speed = 3
        self.floorplan.update_interval = 10
        self.floorplan.set_session(session)
        self.setLayout(VBoxLayout([
            self.floorplan, [
                self._button("Z|X", -pi/2, -pi/2),
                self._button("X|Y",     0,     0),
                self._button("Z|Y", -pi/2,     0),
            ],
        ]))
        # Keep focus on the GL widget, prevent buttons from stealing focus:
        for child in self.findChildren(QWidget):
            child.setFocusPolicy(
                Qt.ClickFocus if child is self.floorplan else Qt.NoFocus)
        self.floorplan.setFocus()

    def _button(self, label, *args):
        button = QPushButton(label)
        button.clicked.connect(lambda: self.floorplan.camera.look_from(*args))
        return button

    def session_data(self):
        return {}

    def closeEvent(self, event):
        self.floorplan.free()
        super().closeEvent(event)


class LatticeFloorPlan(QOpenGLWidget):

    """
    Graphics widget to draw 3D floor plan of given lattice.
    """

    model = None

    background_color = gl_array([1, 1, 1]) * 0.6
    ambient_color = gl_array([1, 1, 1]) * 0.1
    diffuse_color = gl_array([1, 1, 1])
    object_color = gl_array([1.0, 0.5, 0.2])

    camera_speed = 1            # [m/s]
    zoom_speed = 1/10           # [1/deg]
    mouse_sensitivity = 1/100   # [rad/px]
    update_interval = 25        # [ms]

    shader_program = None
    update_timer = None

    def __init__(self, session=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = []
        self._key_state = {}
        self._update_time = QTime()
        self.resize(800, 600)
        self.camera = Camera()
        self.camera.updated.connect(self.update)
        if session is not None:
            self.set_session(session)
        # Enable multisampling (for antialiasing):
        # (must be set before initializeGL)
        surface_format = self.format()
        surface_format.setSamples(6)
        self.setFormat(surface_format)

    def set_session(self, session):
        session.model.changed.connect(self._set_model)
        self._set_model(session.model())

    def free(self):
        for item in self.items:
            item.delete()

    def closeEvent(self, event):
        self.free()
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self.update_timer is None:
            self.update_timer = QTimer(self)
            self.update_timer.setInterval(self.update_interval)
            self.update_timer.timeout.connect(self.update_event)
            self.update_timer.start()
            self._update_time.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self.update_timer is not None:
            self.update_timer.timeout.disconnect(self.update_event)
            self.update_timer.stop()
            self.update_timer = None

    def _set_model(self, model):
        # TODO: only update when SBEND/MULTIPOLE/SROTATION etc changes?
        if self.model:
            self.model.updated.disconnect(self._updateSurvey)
        self.model = model
        if model:
            self.model.updated.connect(self._updateSurvey)
            self._updateSurvey()
        self.create_scene()

    def _updateSurvey(self):
        survey = self.model.survey()
        array = np.array([survey[key] for key in FloorCoords._fields])
        floor = [FloorCoords(*row) for row in array.T]
        self.setElements(self.model.elements, floor)

    # def GL(self):
    #     from PyQt5.QtGui import QOpenGLVersionProfile
    #     version = QOpenGLVersionProfile()
    #     version.setVersion(2, 0)
    #     return self.context().versionFunctions(version)

    def initializeGL(self):
        self.create_shader_program()

        # Activate wireframe:
        # GL.glPolygonMode(GL.GL_FRONT_AND_BACK, GL.GL_LINE)
        camera = self.camera
        camera.look_from(camera.theta, camera.phi, camera.psi)
        self.create_scene()

    def paintGL(self):
        program = self.shader_program
        projection = self.camera.projection(self.width(), self.height())
        set_uniform_matrix(program, "view", self.camera.view_matrix)
        set_uniform_matrix(program, "projection", projection)

        set_uniform_vector(program, "ambient_color", self.ambient_color)
        set_uniform_vector(program, "object_color", self.object_color)
        set_uniform_vector(program, "diffuse_color", self.diffuse_color)
        set_uniform_vector(program, "diffuse_position", self.camera.position)

        GL.glClearColor(*self.background_color, 0)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_MULTISAMPLE)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        for item in self.items:
            item.draw()

    def create_scene(self):
        self.free()
        self.items.clear()
        if self.shader_program is None or not self.model:
            return

        elements = self.elements
        survey = [FloorCoords(0, 0, 0, 0, 0, 0)] + self.survey

        points = np.array([[f.x, f.y, f.z] for f in survey])
        bounds = np.array([np.min(points, axis=0), np.max(points, axis=0)])
        center = np.mean(bounds, axis=0)

        camera = self.camera
        camera.center = center
        camera.distance = np.max(np.linalg.norm(points - center, axis=1)) + 1
        camera.look_from(camera.theta, camera.phi, camera.psi)

        # Show continuous drift tubes through all elements:
        drift_color = QColor(ELEMENT_COLOR['DRIFT'])
        drift_width = ELEMENT_WIDTH['DRIFT']
        self.items[:] = [
            self.create_element_item(
                element, coords, drift_color, drift_width)
            for element, coords in zip(elements, zip(survey, survey[1:]))
            if element.l > 0
        ]
        self.items += [
            self.create_element_item(
                element, coords,
                getElementColor(element),
                getElementWidth(element))
            for element, coords in zip(elements, zip(survey, survey[1:]))
            if element.l > 0 and element.base_name != 'drift'
        ]

    def create_element_item(self, element, coords, color, width):
        start, end = coords

        color = gl_array(color.getRgbF())
        radius = width/2

        # TODO: sanitize rotation...
        rot = rotate(-start.theta, -start.phi, -start.psi)
        tra = translate(start.x, start.y, start.z)
        transform = tra @ rot.T

        angle = float(element.get('angle', 0.0))
        l = element.l

        if angle:
            # this works the same for negative angle!
            r0 = l / angle
            n0 = round(5 * l) + 1
            local_transform = rotate(0, -pi/2, 0) @ translate(-r0, 0, 0)
            return Object3D(
                self.shader_program, transform @ local_transform, color,
                *torus_arc(r0, radius, n0, 20, angle),
                GL.GL_TRIANGLE_STRIP)

        else:
            return Object3D(
                self.shader_program, transform, color,
                *cylinder(l, r=radius, n1=20),
                GL.GL_TRIANGLE_STRIP)

    def create_shader_program(self):
        self.shader_program = create_shader_program([
            load_shader(GL.GL_VERTEX_SHADER, 'shader_vertex.glsl'),
            load_shader(GL.GL_FRAGMENT_SHADER, 'shader_fragment.glsl'),
        ])

    def minimumSizeHint(self):
        return QSize(50, 50)

    def sizeHint(self):
        return QSize(400, 400)

    def setElements(self, elements, survey):
        self.elements = elements
        self.survey = survey

    def resizeEvent(self, event):
        """Maintain visible region on resize."""
        # TODO: scale view area
        super().resizeEvent(event)

    def wheelEvent(self, event):
        """Handle mouse wheel as zoom."""
        delta = event.angleDelta().y()
        self.camera.zoom(delta * self.zoom_speed)

    def mousePressEvent(self, event):
        self.last_mouse_position = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        camera = self.camera
        delta = event.pos() - self.last_mouse_position
        if event.buttons() == Qt.RightButton:
            dx = delta.x() * self.mouse_sensitivity
            dy = delta.y() * self.mouse_sensitivity
            if event.modifiers() & Qt.ShiftModifier:
                camera.look_from(camera.theta + dx, camera.phi + dy, camera.psi)
            else:
                camera.look_toward(camera.theta + dx, camera.phi - dy, camera.psi)
        elif event.buttons() == Qt.RightButton | Qt.LeftButton:
            camera.zoom(-delta.y())
        else:
            return super().mouseMoveEvent(event)
        self.last_mouse_position = event.pos()
        event.accept()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Escape, Qt.Key_Q):
            self.window().close()
        if not event.isAutoRepeat():
            self._key_state[key] = True
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if not event.isAutoRepeat():
            self._key_state[event.key()] = False

    def update_event(self):
        pressed = lambda k: self._key_state.get(k, 0)
        upward = pressed(Qt.Key_Space) - pressed(Qt.Key_Control)
        forward = ((pressed(Qt.Key_Up) or pressed(Qt.Key_W)) -
                   (pressed(Qt.Key_Down) or pressed(Qt.Key_S)))
        leftward = ((pressed(Qt.Key_Left) or pressed(Qt.Key_A)) -
                    (pressed(Qt.Key_Right) or pressed(Qt.Key_D)))

        # we use this "update time" (a.k.a. "game time") to maintain a
        # somewhat framerate independent movement speed:
        ms_elapsed = self._update_time.elapsed()
        self._update_time.start()

        if forward or upward or leftward:
            direction = np.array([-leftward, upward, -forward])
            direction = direction / np.linalg.norm(direction)
            translate = direction * self.camera_speed * (ms_elapsed/1000)
            self.camera.translate(*translate)


def getElementColor(element, default='black'):
    return QColor(ELEMENT_COLOR.get(element.base_name.upper(), default))


def getElementWidth(element, default=0.2):
    return ELEMENT_WIDTH.get(element.base_name.upper(), default)


if __name__ == '__main__':
    from madgui.core.app import main
    main(None, FloorPlanWidget)
