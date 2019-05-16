"""
Components to draw a 3D floor plan of a given MAD-X lattice.
"""

# TODO: entry/exit pole faces
# TODO: load styles from config + UI
# TODO: add exporters for common 3D data formats (obj+mtl/collada/ply?)
# TODO: customize settings via UI (wireframe etc)
# TODO: show thin elements as disks (kicker/monitor)

__all__ = [
    'FloorPlanWidget',
]

from collections import namedtuple
from math import pi

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget, QPushButton

from madgui.util.layout import VBoxLayout

import OpenGL.GL as GL

from .transform import gl_array, rotate, translate
from .shapes import cylinder, torus_arc
from .gl_util import Object3D
from .gl_widget import GLWidget


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

    """A widget that shows a 3D scene of the accelerator."""

    def __init__(self, session):
        super().__init__()
        self.setWindowTitle("3D floor plan")
        self.gl_widget = GLWidget(self.create_items)
        self.gl_widget.camera_speed = 3
        self.gl_widget.update_interval = 10
        self.setLayout(VBoxLayout([
            self.gl_widget, [
                self._button("Z|X", -pi/2, -pi/2),
                self._button("X|Y",     0,     0),
                self._button("Z|Y", -pi/2,     0),
            ],
        ]))
        # Keep focus on the GL widget, prevent buttons from stealing focus:
        for child in self.findChildren(QWidget):
            child.setFocusPolicy(
                Qt.ClickFocus if child is self.gl_widget else Qt.NoFocus)
        self.gl_widget.setFocus()
        self.model = None
        self.set_session(session)

    def _button(self, label, *args):
        button = QPushButton(label)
        button.clicked.connect(lambda: self.gl_widget.camera.look_from(*args))
        return button

    def session_data(self):
        return {}

    def closeEvent(self, event):
        self.gl_widget.free()
        super().closeEvent(event)

    def set_session(self, session):
        """Set session."""
        session.model.changed.connect(self._set_model)
        self._set_model(session.model())

    def _set_model(self, model):
        """Recreates scene after model has changed."""
        # TODO: only update when SBEND/MULTIPOLE/SROTATION etc changes?
        if self.model:
            self.model.updated.disconnect(self._updateSurvey)
        self.model = model
        if model:
            self.model.updated.connect(self._updateSurvey)
            self._updateSurvey()

    def _updateSurvey(self):
        """Recreate and update the scene."""
        survey = self.model.survey()
        array = np.array([survey[key] for key in FloorCoords._fields])
        floor = [FloorCoords(*row) for row in array.T]
        self.setElements(self.model.elements, floor)

    def setElements(self, elements, survey):
        """Set scene using given elements and floor coordinates."""
        self.elements = elements
        self.survey = survey
        self.gl_widget.create_scene()

    def create_items(self, camera):
        """Turn the MAD-X sequence of elements into a list of ``Object3D``
        constituting the scene to be drawn."""
        if not self.model:
            return []

        elements = self.elements
        survey = [FloorCoords(0, 0, 0, 0, 0, 0)] + self.survey

        points = np.array([[f.x, f.y, f.z] for f in survey])
        bounds = np.array([np.min(points, axis=0), np.max(points, axis=0)])
        center = np.mean(bounds, axis=0)

        camera.center = center
        camera.distance = np.max(np.linalg.norm(points - center, axis=1)) + 1
        camera.look_from(camera.theta, camera.phi, camera.psi)

        # Show continuous drift tubes through all elements:
        drift_color = QColor(ELEMENT_COLOR['DRIFT'])
        drift_width = ELEMENT_WIDTH['DRIFT']
        drift_pipes = [
            self.create_element_item(
                element, coords, drift_color, drift_width)
            for element, coords in zip(elements, zip(survey, survey[1:]))
            if element.l > 0
        ]
        other_elements = [
            self.create_element_item(
                element, coords,
                getElementColor(element),
                getElementWidth(element))
            for element, coords in zip(elements, zip(survey, survey[1:]))
            if element.l > 0 and element.base_name != 'drift'
        ]
        return drift_pipes + other_elements

    def create_element_item(self, element, coords, color, width):
        """Create an ``Object3D`` for a single beam line element. Use the
        supplied color and tube diameter."""
        start, end = coords

        color = gl_array(color.getRgbF())
        radius = width/2

        # TODO: sanitize rotation...
        rot = rotate(-start.theta, -start.phi, -start.psi)
        tra = translate(start.x, start.y, start.z)
        transform = tra @ rot.T

        angle = float(element.get('angle', 0.0))
        l = element.l

        shader_program = self.gl_widget.shader_program
        if angle:
            # this works the same for negative angle!
            r0 = l / angle
            n0 = round(5 * l) + 1
            local_transform = rotate(0, -pi/2, 0) @ translate(-r0, 0, 0)
            return Object3D(
                shader_program, transform @ local_transform, color,
                *torus_arc(r0, radius, n0, 20, angle),
                GL.GL_TRIANGLE_STRIP)

        else:
            return Object3D(
                shader_program, transform, color,
                *cylinder(l, r=radius, n1=20),
                GL.GL_TRIANGLE_STRIP)


def getElementColor(element, default='black'):
    """Lookup element color."""
    return QColor(ELEMENT_COLOR.get(element.base_name.upper(), default))


def getElementWidth(element, default=0.2):
    """Lookup element tube size (in meters)."""
    return ELEMENT_WIDTH.get(element.base_name.upper(), default)


if __name__ == '__main__':
    from madgui.core.app import main
    main(None, FloorPlanWidget)
