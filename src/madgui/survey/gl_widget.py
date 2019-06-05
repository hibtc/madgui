"""
Contains a OpenGL widget to display a static scene.
"""

__all__ = [
    'GLWidget',
]

import logging
from contextlib import contextmanager

import numpy as np
from PyQt5.QtCore import Qt, QSize, QTimer, QTime
from PyQt5.QtWidgets import QOpenGLWidget
from PyQt5.QtGui import QOffscreenSurface, QOpenGLContext, QSurfaceFormat

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

    camera_speed = 1            # [m/s]
    zoom_speed = 1/10           # [1/deg]
    mouse_sensitivity = 1/100   # [rad/px]
    update_interval = 25        # [ms]

    shader_program = None
    update_timer = None

    def __init__(self, create_items, *args, **kwargs):
        """Create from a callable ``create_items: Camera -> [Object3D]``."""
        super().__init__(*args, **kwargs)
        self._create_items = create_items
        self.items = []
        self._key_state = {}
        self._update_time = QTime()
        self.resize(800, 600)
        self.camera = Camera()
        self.camera.updated.connect(self.update)
        surface_format = self.format()
        # Enable multisampling (for antialiasing):
        # (must be set before initializeGL)
        surface_format.setSamples(6)
        # Technically, we require only 3.0, but we request 3.2 because that
        # allows enforcing CoreProfile. Note that there is no guarantee that
        # we get the requested version, but let's at least improve our chances:
        surface_format.setVersion(3, 2)
        surface_format.setProfile(QSurfaceFormat.CoreProfile)
        self.setFormat(surface_format)

    def free(self):
        """Free all items."""
        for item in self.items:
            item.delete()
        self.items.clear()

    def closeEvent(self, event):
        """Free items."""
        self.free()
        super().closeEvent(event)

    def showEvent(self, event):
        """Start scene updates (camera movement)."""
        super().showEvent(event)
        if self.update_timer is None:
            self.update_timer = QTimer(self)
            self.update_timer.setInterval(self.update_interval)
            self.update_timer.timeout.connect(self.update_event)
            self.update_timer.start()
            self._update_time.start()

    def hideEvent(self, event):
        """Stop scene updates (camera movement)."""
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
        """Called after first creating a valid OpenGL context. Creates shader
        program, sets up camera and creates an initial scene."""
        logging.info('Initializing OpenGL')
        self.show_gl_info(GL.GL_VERSION,  '  version:  ')
        self.show_gl_info(GL.GL_VENDOR,   '  vendor:   ')
        self.show_gl_info(GL.GL_RENDERER, '  renderer: ')
        self.show_gl_info(GL.GL_SHADING_LANGUAGE_VERSION, '  shader:   ')
        logging.info('  context:  {}.{}'.format(
            *self.context().format().version()))
        # We currently require modern OpenGL API for use of shaders etc. We
        # could ship a fallback implementation based on the deprecated API
        # (glBegin, etc) to be compatible with older devices, but that's
        # probably overkill.
        if not check_opengl_context(self.context(), (3, 0)):
            logging.error(
                "Cannot create shader with this version of OpenGL.\n"
                "This implementation uses the modern OpenGL API (>=3.0).")
            QTimer.singleShot(0, lambda: self.window().close())
            return
        self.create_shader_program()
        self.create_scene()
        # Activate wireframe:
        # GL.glPolygonMode(GL.GL_FRONT_AND_BACK, GL.GL_LINE)
        camera = self.camera
        camera.look_from(camera.theta, camera.phi, camera.psi)

    def show_gl_info(self, spec, text):
        """Show GL version info."""
        try:
            string = GL.glGetString(spec).decode('utf-8')
        except GL.GLError:
            string = None
        if string:
            logging.info(text + string)
        else:
            logging.error(text + 'N/A')
        return string

    def create_scene(self):
        """Fetch new items from the given callable."""
        self.free()
        if self.shader_program is not None:
            self.items = self._create_items(self.camera)
            self.update()

    def paintGL(self):
        """Handle paint event by drawing the items returned by the creator
        function."""
        if not check_opengl_context(self.context(), (3, 0)):
            return
        program = self.shader_program
        projection = self.camera.projection(self.width(), self.height())
        set_uniform_matrix(program, "view", self.camera.view_matrix)
        set_uniform_matrix(program, "projection", projection)

        set_uniform_vector(program, "ambient_color", self.ambient_color)
        set_uniform_vector(program, "diffuse_color", self.diffuse_color)
        set_uniform_vector(program, "diffuse_position", self.camera.position)

        GL.glClearColor(*self.background_color, 0)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_MULTISAMPLE)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        # Draw transparent items after opaque ones, and sorted by distance to
        # the observer (far to near). Note that this is only an approximation
        # that is correct only for point-like items; a 100% correct blending
        # order would have to be decided on the level of fragments (based on
        # the interpolated depth value).
        items = sorted(self.items, key=lambda item: (
            item.opaque(),
            np.linalg.norm(self.camera.position - item.position()),
        ), reverse=True)
        for item in items:
            item.draw()

    def create_shader_program(self):
        """Create simple program with generic fragment/vertex shaders used to
        render objects with a simple ambient+diffuse lighting model."""
        self.shader_program = create_shader_program([
            load_shader(GL.GL_VERTEX_SHADER, 'shader_vertex.glsl'),
            load_shader(GL.GL_FRAGMENT_SHADER, 'shader_fragment.glsl'),
        ])

    def minimumSizeHint(self):
        return QSize(50, 50)

    def sizeHint(self):
        return QSize(400, 400)

    def wheelEvent(self, event):
        """Handle mouse wheel as zoom."""
        self.camera.zoom(self.zoom_speed * event.angleDelta().y())

    def mousePressEvent(self, event):
        """Handle camera look around."""
        self.last_mouse_position = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle camera look around."""
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
        """Maintain a list of pressed keys for camera movement."""
        key = event.key()
        if key in (Qt.Key_Escape, Qt.Key_Q):
            self.window().close()
        if not event.isAutoRepeat():
            self._key_state[key] = True
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Maintain a list of pressed keys for camera movement."""
        if not event.isAutoRepeat():
            self._key_state[event.key()] = False

    def update_event(self):
        """Implement camera movement. Called regularly."""
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


@contextmanager
def offscreen_context(format):
    """Provide a temporary QOpenGLContext with the given QSurfaceFormat on an
    QOffscreenSurface."""
    surface = QOffscreenSurface()
    surface.create()
    context = QOpenGLContext()
    context.setFormat(format)
    context.create()
    context.makeCurrent(surface)
    try:
        yield context
    finally:
        context.doneCurrent()


def check_opengl_context(context, version):
    """Check whether the active OpenGL context suffices our requirements."""
    # Note that in some cases `context.format().version()` is not updated to
    # hold the actual OpenGL version, which is why we need additional checks
    # like the availability of glCreateShader and the glGetString based
    # version detection:
    return (
        context and
        context.isValid() and
        context.format().version() >= version and
        bool(GL.glCreateShader) and
        gl_version() >= version)


def gl_version():
    """Return active OpenGL version as determined by glGetString."""
    try:
        version_string = GL.glGetString(GL.GL_VERSION).decode('utf-8')
    except GL.GLError:
        # This fails on control system PCs:
        version_string = '0.0'
    major, minor = version_string.split(' ')[0].split('.')[:2]
    return (int(major), int(minor))
