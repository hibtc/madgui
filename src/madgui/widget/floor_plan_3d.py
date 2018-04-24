"""
Components to draw a 3D floor plan of a given MAD-X lattice.
"""

# TODO: improve camera movement
# TODO: entry/exit pole faces
# TODO: load styles from config + UI
# TODO: improve camera movement: first person vs. panning
# TODO: add exporters for common 3D data formats (obj+mtl/collada/ply?)
# TODO: customize settings via UI (wireframe etc)
# TODO: show thin elements as disks (kicker/monitor)

__all__ = [
    'LatticeFloorPlan',
]

from collections import namedtuple
from math import pi
import textwrap

from importlib_resources import read_binary

import numpy as np
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QColor, QMatrix4x4, QVector3D
from PyQt5.QtWidgets import QWidget, QPushButton, QOpenGLWidget

from madgui.util.layout import VBoxLayout

import OpenGL.GL as GL


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


def rotate(theta, phi, psi):
    """Return a rotation matrix for rotation angles as defined in MAD-X."""
    mat = QMatrix4x4()
    mat.rotate(180/pi * psi,   0, 0, 1)
    mat.rotate(180/pi * -phi,  1, 0, 0)
    mat.rotate(180/pi * theta, 0, 1, 0)
    return qmatrix_to_numpy(mat)


def translate(dx, dy, dz):
    """Return a translation matrix."""
    mat = QMatrix4x4()
    mat.translate(dx, dy, dz)
    return qmatrix_to_numpy(mat)


def perspective_projection(fov, aspect_ratio, near_plane, far_plane):
    mat = QMatrix4x4()
    mat.perspective(fov, aspect_ratio, near_plane, far_plane)
    return qmatrix_to_numpy(mat)


def look_at(position, target, up):
    mat = QMatrix4x4()
    mat.lookAt(
        QVector3D(*position[:3]),
        QVector3D(*target[:3]),
        QVector3D(*up[:3]))
    return qmatrix_to_numpy(mat)


def qmatrix_to_numpy(qmatrix):
    return np.array(qmatrix.data(), dtype=np.float32).reshape((4, 4)).T


class FloorPlanWidget(QWidget):

    def __init__(self, session):
        super().__init__()
        self.setWindowTitle("3D floor plan")
        self.floorplan = LatticeFloorPlan()
        self.floorplan.set_session(session)
        self.setLayout(VBoxLayout([
            self.floorplan, [
                self._button("Z|X", -pi/2, -pi/2),
                self._button("X|Y",     0,     0),
                self._button("Z|Y", -pi/2,     0),
            ],
        ]))

    def _button(self, label, *args):
        button = QPushButton(label)
        button.clicked.connect(lambda: self.floorplan.set_camera(*args))
        return button

    def session_data(self):
        return {}


class LatticeFloorPlan(QOpenGLWidget):

    """
    Graphics widget to draw 3D floor plan of given lattice.
    """

    model = None

    distance = 3
    theta = -pi/2
    phi = -pi/2
    psi = 0

    fov = 70.0
    near = 0.01
    far = 1000

    center = np.array([0, 0, 0], dtype=np.float32)

    background_color = np.array([1, 1, 1], dtype=np.float32) * 0.6
    ambient_color = np.array([1, 1, 1], dtype=np.float32) * 0.1
    diffuse_color = np.array([1, 1, 1], dtype=np.float32)
    object_color = np.array([1.0, 0.5, 0.2], dtype=np.float32)

    shader_program = None

    def __init__(self, session=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = []
        self.resize(800, 600)
        if session is not None:
            self.set_session(session)

    def set_session(self, session):
        session.model.changed.connect(self._set_model)
        self._set_model(session.model())

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
        self.set_camera(self.theta, self.phi, self.psi)
        self.create_scene()

    def paintGL(self):
        program = self.shader_program
        projection = self.get_perspective_projection()
        set_uniform_matrix(program, "view", self.view)
        set_uniform_matrix(program, "projection", projection)

        set_uniform_vector(program, "ambient_color", self.ambient_color)
        set_uniform_vector(program, "object_color", self.object_color)
        set_uniform_vector(program, "diffuse_color", self.diffuse_color)
        set_uniform_vector(program, "diffuse_position", self.camera_position)

        GL.glClearColor(*self.background_color, 0)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        for item in self.items:
            item.draw()

    def create_scene(self):
        for item in self.items:
            item.delete()
        self.items.clear()
        if self.shader_program is None or not self.model:
            return

        elements = self.elements
        survey = [FloorCoords(0, 0, 0, 0, 0, 0)] + self.survey

        points = np.array([[f.x, f.y, f.z] for f in survey])
        bounds = np.array([np.min(points, axis=0), np.max(points, axis=0)])
        center = np.mean(bounds, axis=0)
        self.center = center
        self.distance = np.max(np.linalg.norm(points - center, axis=1)) + 1

        self.set_camera(self.theta, self.phi, self.psi)

        self.items[:] = [
            self.create_element_item(element, coords)
            for element, coords in zip(elements, zip(survey, survey[1:]))
            if element.l > 0
        ]

    def create_element_item(self, element, coords):
        start, end = coords
        color = np.array(getElementColor(element).getRgbF(), dtype=np.float32)
        radius = getElementWidth(element)/2

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
                *torus_arc(r0, radius, n0, 20, angle))

        else:
            return Object3D(
                self.shader_program, transform, color,
                *cylinder(l, r=radius, n1=20))

    def create_shader_program(self):
        self.shader_program = create_shader_program([
            load_shader(GL.GL_VERTEX_SHADER, 'floor_plan_3d.vert.glsl'),
            load_shader(GL.GL_FRAGMENT_SHADER, 'floor_plan_3d.frag.glsl'),
        ])

    def get_perspective_projection(self):
        return perspective_projection(
            self.fov, self.width()/self.height(), self.near, self.far)

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

    def zoom(self, scale):
        """Scale the figure uniformly along both axes."""
        self.fov = np.clip(self.fov - scale/5, 1.0, 180.0)
        self.update()

    def set_camera(self, theta, phi, psi=0):
        # Prevent from rotating into upside-down camera orientation:
        phi = np.clip(phi, -pi/2, pi/2)
        rot = rotate(theta, phi, psi)
        tra0 = translate(*-self.center)
        tra1 = translate(0, 0, -self.distance)
        self.theta, self.phi, self.psi = theta, phi, psi
        self.view = tra1 @ rot @ tra0
        self.camera_position = \
            -self.view @ np.array([0, 0, 0, 1], dtype=np.float32)
        self.update()

    def wheelEvent(self, event):
        """Handle mouse wheel as zoom."""
        delta = event.angleDelta().y()
        self.zoom(delta/10.0)

    def mousePressEvent(self, event):
        self.last_mouse_position = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        delta = event.pos() - self.last_mouse_position
        if event.buttons() == Qt.RightButton:
            theta = self.theta + delta.x()/100
            phi = self.phi + delta.y()/100
            self.set_camera(theta, phi, self.psi)
        elif event.buttons() == Qt.RightButton | Qt.LeftButton:
            self.zoom(-delta.y())
        else:
            return super().mouseMoveEvent(event)
        self.last_mouse_position = event.pos()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Q):
            self.window().close()
        else:
            super().keyPressEvent(event)


class Object3D:

    def __init__(self, program, transform, color,
                 vertices, normals, triangles, mode=GL.GL_TRIANGLES):
        self.program = program
        self.deleted = False
        self.transform = transform
        self.color = color
        self.mode = mode
        ploc = GL.glGetAttribLocation(program, "position")
        nloc = GL.glGetAttribLocation(program, "normal")
        vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(vao)
        self.vbo = setup_vertex_buffer(ploc, vertices)
        self.ebo = setup_element_buffer(triangles)
        self.nbo = setup_vertex_buffer(nloc, normals)
        self.vao = vao
        self.num = triangles.size

    def draw(self):
        GL.glUseProgram(self.program)
        set_uniform_vector(self.program, "object_color", self.color)
        set_uniform_matrix(self.program, "model", self.transform)
        GL.glBindVertexArray(self.vao)
        GL.glDrawElements(self.mode, self.num, GL.GL_UNSIGNED_INT, None)

    def __del__(self):
        self.delete()

    def delete(self):
        if not self.deleted:
            self.deleted = True
            GL.glDeleteBuffers(1, [self.vbo])
            GL.glDeleteBuffers(1, [self.nbo])
            GL.glDeleteBuffers(1, [self.ebo])
            GL.glDeleteVertexArrays(1, [self.vao])


def cylinder(l, r, n1, n0=2):
    z0 = np.zeros(n0, dtype=np.float32)[:, None]
    t0 = np.linspace(0, l,    n0, dtype=np.float32)[:, None]
    t1 = np.linspace(0, 2*pi, n1, dtype=np.float32)[None, :]
    centers = np.stack([z0, z0, t0])
    normals = np.stack([
        np.cos(t1),
        np.sin(t1),
        0 * t1,
    ]) + z0
    vertices = centers + r * normals
    return _tube_strip(vertices, normals)


def torus_arc(r0, r1, n0, n1, ang0=2*pi, ang1=2*pi):
    """
    Return (vertices, normals, draw indices, mode) of rounded pipe a.k.a. torus
    with x-y plane symmetry centered at ``(0, 0, 0)``.

    The returned vertices are generated by revolving a circular segment C1
    about the coplanar z axis, with C1's center coordinates being described by
    the circular segment C0. Both circular segments are desribed by triples:

        (r, n, ang) = (radius, num_points, angle).
    """
    # e_phi = (cos(s0), sin(s0), 0)
    # e_z   = (0, 0, 1)
    # center = r * e_phi
    # phi, z = cos(s1), sin(s1)
    # result = center + phi * e_phi + z * e_z
    z0 = np.zeros(n0, dtype=np.float32)[:, None]
    t0 = np.linspace(0, ang0, n0, dtype=np.float32)[:, None]
    t1 = np.linspace(0, ang1, n1, dtype=np.float32)[None, :]
    c0, s0 = np.cos(t0), np.sin(t0)
    c1, s1 = np.cos(t1), np.sin(t1)
    centers = np.stack([c0, s0, z0]) * r0
    normals = np.stack([
        c1 * c0,
        c1 * s0,
        s1 + z0,
    ])
    vertices = centers + r1 * normals
    return _tube_strip(vertices, normals)


def _tube_strip(vertices, normals):
    n0, n1 = vertices.shape[1:]
    indices = np.arange(n0 * n1, dtype=np.uint32).reshape((n0, n1))
    strips = np.stack((
        indices[:-1, :],
        indices[+1:, :],
    ))
    vertices = vertices.transpose((1, 2, 0)).reshape((-1, 3))
    normals = normals.transpose((1, 2, 0)).reshape((-1, 3))
    strips = strips.transpose((1, 2, 0)).reshape((-1,))
    return vertices, normals, strips, GL.GL_TRIANGLE_STRIP


def getElementColor(element, default='black'):
    return QColor(ELEMENT_COLOR.get(element.base_name.upper(), default))


def getElementWidth(element, default=0.2):
    return ELEMENT_WIDTH.get(element.base_name.upper(), default)


def compile_shader(type, source):
    """Compile a OpenGL shader, and return its id."""
    shader_id = GL.glCreateShader(type)
    GL.glShaderSource(shader_id, source)
    GL.glCompileShader(shader_id)
    if not GL.glGetShaderiv(shader_id, GL.GL_COMPILE_STATUS):
        info = GL.glGetShaderInfoLog(shader_id).decode('utf-8')
        raise RuntimeError("OpenGL {} shader compilation error:\n{}".format(
            type, textwrap.indent(info, "    ")))
    return shader_id


def load_shader(type, name):
    return compile_shader(type, read_binary(__package__, name))


def create_shader_program(shaders):
    shader_program = GL.glCreateProgram()
    for shader in shaders:
        GL.glAttachShader(shader_program, shader)
        GL.glDeleteShader(shader)
    GL.glLinkProgram(shader_program)
    if not GL.glGetProgramiv(shader_program, GL.GL_LINK_STATUS):
        info = GL.glGetProgramInfoLog(shader_program).decode('utf-8')
        raise RuntimeError("OpenGL program link error:\n{}".format(
            textwrap.indent(info, "    ")))
    return shader_program


def setup_vertex_buffer(loc, data):
    """Set program attribute from vertex buffer."""
    num = data.shape[1]
    flat = data.reshape(-1)
    vbo = GL.glGenBuffers(1)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
    GL.glBufferData(GL.GL_ARRAY_BUFFER, flat.nbytes, flat, GL.GL_STATIC_DRAW)
    GL.glVertexAttribPointer(loc, num, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
    GL.glEnableVertexAttribArray(loc)
    return vbo


def setup_element_buffer(indices):
    ebo = GL.glGenBuffers(1)
    GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, ebo)
    GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices,
                    GL.GL_STATIC_DRAW)
    # don't unbind EBO with active VAO:
    # GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, 0)
    return ebo


def set_uniform_matrix(program, name, matrix):
    GL.glUseProgram(program)
    loc = GL.glGetUniformLocation(program, name)
    GL.glUniformMatrix4fv(loc, 1, GL.GL_FALSE, matrix.ravel('F'))


def set_uniform_vector(program, name, vector):
    GL.glUseProgram(program)
    loc = GL.glGetUniformLocation(program, name)
    GL.glUniform3fv(loc, 1, vector)


if __name__ == '__main__':
    from madgui.core.app import main
    main(None, FloorPlanWidget)
