"""
This module defines the toplevel context that is used in madgui to keep track
of current model, config, online control, and mainwindow.
"""

__all__ = [
    'Session',
]

import glob
import os
import sys
from types import SimpleNamespace

import numpy as np

from madgui.util.collections import Boxed, Selection
from madgui.util.misc import relpath, userpath
from madgui.online.control import Control
from madgui.core.config import load as load_config
from madgui.model.match import Matcher
import madgui.util.yaml as yaml


class Session:

    """
    Context variables and top-level application logic for a madgui session,
    i.e. the interaction between user and different parts of the computer
    program. This object keeps track and coordinates the use of the currently
    opened model, GUI window, user variables, control system connection, and
    configuration data.
    """

    def __init__(self, config=None):
        if config is None:
            config = load_config()
        self.config = config
        self.window = Boxed(None)
        self.model = Boxed(None)
        self.control = Control(self)
        self.matcher = None
        self.user_ns = user_ns = SimpleNamespace()
        self.session_file = userpath(config.session_file)
        self.folder = userpath(config.model_path)
        self.selected_elements = Selection()
        self.model.changed2.connect(self.on_model_changed)
        # Maintain these members into the namespace
        subscribe(user_ns, 'model', self.model)
        subscribe(user_ns, 'window', self.window)
        user_ns.config = config
        user_ns.context = self
        user_ns.control = self.control

    def on_model_changed(self, old, new):
        self.selected_elements.clear()
        if old:
            self.matcher = None
            old.destroy()
        if new:
            self.matcher = Matcher(new, self.config.get('matching'))

    def set_interpolate(self, points_per_meter):
        self.config.interpolate = points_per_meter
        model = self.model()
        if model:
            model.interpolate = points_per_meter
            model.invalidate()

    def configure(self):
        paths = self.config.get('run_path', [])
        paths = [paths] if isinstance(paths, str) else paths
        for path in paths:
            os.environ['PATH'] += os.pathsep + userpath(path)
        paths = self.config.get('import_path', [])
        paths = [paths] if isinstance(paths, str) else paths
        for path in paths:
            sys.path.append(userpath(path))
        np.set_printoptions(**self.config['printoptions'])
        exec(self.config.onload, self.user_ns.__dict__)

    def terminate(self):
        if self.session_file:
            self.save(self.session_file)
            self.session_file = None
        if self.control.is_connected():
            self.control.disconnect()
        self.model.set(None)
        self.window.set(None)

    def load_default(self, model=None):
        self.configure()
        config = self.config
        filename = model or config.load_default
        if filename:
            self.load_model(filename)
        if self.control.can_connect() and config.online_control.connect:
            self.control.connect()

    def load_model(self, name, **madx_args):
        filename = self.find_model(name)
        exts = ('.cpymad.yml', '.madx', '.str', '.seq')
        if not filename.endswith(exts):
            raise NotImplementedError("Unsupported file format: {}"
                                      .format(filename))
        from madgui.model.madx import Model
        self.model.set(Model.load_file(
            filename, **dict(self.model_args(filename), **madx_args)))

    known_extensions = ['.cpymad.yml', '.madx']

    def find_model(self, name):
        for path in [name, os.path.join(self.folder or '.', name)]:
            if os.path.isdir(path):
                models = (glob.glob(os.path.join(path, '*.cpymad.yml')) +
                          glob.glob(os.path.join(path, '*.madx')))
                if models:
                    return models[0]
            path = expand_ext(path, '', *self.known_extensions)
            if os.path.isfile(path):
                return path
        raise OSError("File not found: {!r}".format(name))

    def model_args(self, filename):
        """Please OVERRIDE to provide custom model arguments."""
        return {'interpolate': self.config.interpolate}

    def save(self, filename):
        """Save session state to file."""
        yaml.save_file(filename, self.session_data())

    def session_data(self):
        folder = self.config.model_path or self.folder
        default = self.model() and relpath(self.model().filename, folder)
        data = {
            'online_control': {
                'backend': self.control.backend_spec,
                'connect': self.control.is_connected(),
                'monitors': self.config.online_control['monitors'],
                'offsets': self.config.online_control['offsets'],
                'settings': self.control.export_settings() or {},
            },
            'model_path': folder,
            'load_default': default,
            'number': self.config['number'],
        }
        if self.window():
            data.update(self.window().session_data())
        return data


def subscribe(ns, key, boxed):
    """Update ``ns[key]`` with the current value of a ``Boxed``."""
    setter = lambda val: setattr(ns, key, val)
    setter(boxed())
    boxed.changed.connect(setter)


def expand_ext(path, *exts):
    """Add the first of the given file extensions ``exts`` to ``path`` that
    refers to an existing file."""
    for ext in exts:
        if os.path.isfile(path+ext):
            return path+ext
    return path
