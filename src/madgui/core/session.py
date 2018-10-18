import glob
import os
from types import SimpleNamespace

import numpy as np

from madgui.util.collections import Boxed
from madgui.util.misc import relpath
from madgui.online.control import Control
from madgui.core.config import load as load_config
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
        self.user_ns = user_ns = SimpleNamespace()
        self.session_file = config.session_file
        self.folder = config.model_path
        self.model.changed[object, object].connect(
            lambda old, new: old and old.destroy())
        # Maintain these members into the namespace
        subscribe(user_ns, 'model', self.model)
        subscribe(user_ns, 'window', self.window)
        user_ns.config = config
        user_ns.context = self
        user_ns.control = self.control

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.terminate()

    def configure(self):
        runtime = self.config.get('runtime_path', [])
        runtime = [runtime] if isinstance(runtime, str) else runtime
        for path in runtime:
            os.environ['PATH'] += os.pathsep + os.path.abspath(path)
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
            self.load_model(self.find_model(filename))
        if self.control.can_connect() and config.online_control.connect:
            self.control.connect()

    def load_model(self, filename, **madx_args):
        exts = ('.cpymad.yml', '.madx', '.str', '.seq')
        if not any(map(filename.endswith, exts)):
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
        return {}

    def save(self, filename):
        """Save session state to file."""
        data = self.session_data()
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'wt') as f:
            yaml.safe_dump(data, f, default_flow_style=False)

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
    setter = lambda val: setattr(ns, key, val)
    setter(boxed())
    boxed.changed.connect(setter)


def expand_ext(path, *exts):
    for ext in exts:
        if os.path.isfile(path+ext):
            return path+ext
    return path
