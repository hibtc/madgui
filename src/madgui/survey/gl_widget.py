"""
Contains a OpenGL widget to display a static scene.
"""

__all__ = [
    'GLWidget',
]

import numpy as np
from PyQt5.QtCore import Qt, QSize, QTimer, QTime
from PyQt5.QtWidgets import QOpenGLWidget

import OpenGL.GL as GL

from .transform import gl_array
from .camera import Camera
from .gl_util import (
    load_shader, create_shader_program,
    set_uniform_matrix, set_uniform_vector)


class GLWidget(QOpenGLWidget):

    """
    OpenGL widget that shows a static 3D scene, allowing the observer to
    freely move and look around.
    """

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

    def __init__(self, create_items, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_items = create_items
        self.items = []
        self._key_state = {}
        self._update_time = QTime()
        self.resize(800, 600)
        self.camera = Camera()
        self.camera.updated.connect(self.update)
        # Enable multisampling (for antialiasing):
        # (must be set before initializeGL)
        surface_format = self.format()
        surface_format.setSamples(6)
        self.setFormat(surface_format)

    def free(self):
        for item in self.items:
            item.delete()
        self.items.clear()

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

    def create_scene(self):
        self.free()
        if self.shader_program is not None:
            self.items = self._create_items(self.camera)

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

    def create_shader_program(self):
        self.shader_program = create_shader_program([
            load_shader(GL.GL_VERTEX_SHADER, 'shader_vertex.glsl'),
            load_shader(GL.GL_FRAGMENT_SHADER, 'shader_fragment.glsl'),
        ])

    def minimumSizeHint(self):
        return QSize(50, 50)

    def sizeHint(self):
        return QSize(400, 400)

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
                camera.look_from(camera.theta + dx, camera.phi - dy, camera.psi)
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
