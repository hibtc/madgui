"""
Must be imported for side effects to initialize matplotlib for use with PyQt
before importing :mod'`matplotlib.backends`!
"""

__all__ = ['mpl_backend']

import madgui.qt            # noqa: F401 import Qt before matplotlib!
import matplotlib as mpl
mpl.use('Qt5Agg')           # noqa: E402 select before mpl.backends import!

import matplotlib.backends.backend_qt5agg as mpl_backend
