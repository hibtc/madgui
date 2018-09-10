"""
Must be imported for side effects to initialize matplotlib for use with PyQt
before importing :mod'`matplotlib.backends`!
"""

__all__ = ['get_backend_module']

import madgui.qt                        # import Qt before matplotlib!
import matplotlib as mpl

mpl.use('Qt5Agg')                       # select before mpl.backends import!
madgui.qt                               # use name to shut up pyflakes


def get_backend_module():
    import matplotlib.backends.backend_qt5agg as mpl_backend
    return mpl_backend
