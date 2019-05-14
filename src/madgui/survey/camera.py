"""
Utilities for dealing with coordinate system / camera transformations.
"""

from math import pi
import numpy as np

from PyQt5.QtCore import QObject, pyqtSignal

from .transform import (
    gl_array, translate, rotate, inverted, perspective_projection)


ORIGIN = gl_array([0, 0, 0, 1])


class Camera(QObject):

    updated = pyqtSignal()

    distance = 1

    # camera angle
    theta = 0
    phi = 0
    psi = 0

    # perspective
    fov = 70.0
    near = 0.01
    far = 1000

    def __init__(self):
        super().__init__()
        self.position = gl_array([0, 0, -1])
        self.center = gl_array([0, 0, 0])
        self.theta = self.phi = self.psi = 0

    def zoom(self, scale):
        """Scale the figure uniformly along both axes."""
        self.fov = np.clip(self.fov - scale/5, 1.0, 180.0)
        self.updated.emit()

    def look_from(self, theta, phi, psi=0):
        """Set camera position by rotating camera around its view target. The
        angles are the coordinates of the camera relative to the target, at a
        distance ``self.distance``."""
        phi = np.clip(phi, -pi/2, pi/2)
        rot = rotate(theta, phi, psi)
        tra0 = translate(*self.center)
        tra1 = translate(0, 0, self.distance)
        goto_camera = tra0 @ rot.T @ tra1
        self.position = (goto_camera @ ORIGIN)[:3]
        self.view_matrix = inverted(goto_camera)
        self.theta, self.phi, self.psi = theta, phi, psi
        self.updated.emit()

    def look_toward(self, theta, phi, psi=0):
        """Rotate camera at fixed position. The center of view is recalculated
        to be at distance ``self.distance`` from the camera position in the
        direction given by the angles."""
        phi = np.clip(phi, -pi/2, pi/2)
        rot = rotate(theta, phi, psi)
        tra0 = translate(*self.position)
        tra1 = translate(0, 0, -self.distance)
        self.center = (tra0 @ rot.T @ tra1 @ ORIGIN)[:3]
        self.view_matrix = tra1 @ rot @ translate(*-self.center)
        self.theta, self.phi, self.psi = theta, phi, psi
        self.updated.emit()

    def translate(self, dx, dy, dz):
        """Move camera position and its view center along the local coordinate
        system. Keeps angles fixed."""
        rot = rotate(self.theta, self.phi, self.psi)
        tra = translate(dx, dy, dz)
        move = rot.T @ tra @ rot
        self.center = (move @ gl_array([*self.center, 1]))[:3]
        self.position = (move @ gl_array([*self.position, 1]))[:3]
        self.look_toward(self.theta, self.phi, self.psi)

    def projection(self, width, height):
        """Return a perspective projection matrix for a viewport with the
        given size."""
        return perspective_projection(
            self.fov, width/height, self.near, self.far)
