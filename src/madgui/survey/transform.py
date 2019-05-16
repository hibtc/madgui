from math import pi
import numpy as np

from PyQt5.QtGui import QMatrix4x4, QVector3D


def gl_array(data):
    """Create a PyOpenGL compatible numpy array from list data."""
    return np.array(data, dtype=np.float32)


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
    """Return a perspective projection matrix."""
    mat = QMatrix4x4()
    mat.perspective(fov, aspect_ratio, near_plane, far_plane)
    return qmatrix_to_numpy(mat)


def look_at(position, target, up):
    """Return transformation matrix for a camera with specified position, view
    target and upwards direction."""
    mat = QMatrix4x4()
    mat.lookAt(
        QVector3D(*position[:3]),
        QVector3D(*target[:3]),
        QVector3D(*up[:3]))
    return qmatrix_to_numpy(mat)


def qmatrix_to_numpy(qmatrix):
    """Convert a QMatrix4x4 to a numpy array."""
    return gl_array(qmatrix.data()).reshape((4, 4)).T


def inverted(matrix):
    """Invert a coordinate system transformation ``M = T @ R`` ."""
    R = np.eye(4, dtype=np.float32)
    T = np.eye(4, dtype=np.float32)
    R[:3, :3] = matrix[:3, :3].T
    T[:3, 3] = -matrix[:3, 3]
    return R @ T
