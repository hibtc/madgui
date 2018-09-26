import glob
import os
from types import SimpleNamespace

import numpy as np

from madgui.util.collections import Boxed
from madgui.online.control import Control
import madgui.core.config as config


class Session:

    """
    Context variables for a madgui session.
    """

    capture_stdout = None

    def __init__(self, options):
        self.options = options
        self.config = config.load(options['--config'])
        self.window = Boxed(None)
        self.model = Boxed(None)
        self.control = Control(self)
        self.user_ns = user_ns = SimpleNamespace()
        self.folder = self.config.model_path
        # Maintain these members into the namespace
        subscribe(user_ns, 'model', self.model)
        subscribe(user_ns, 'window', self.window)
        user_ns.config = self.config
        user_ns.context = self
        user_ns.control = self.control
        # global side-effects…:
        config.number = self.config.number

    def configure(self):
        runtime = self.config.get('runtime_path', [])
        runtime = [runtime] if isinstance(runtime, str) else runtime
        for path in runtime:
            os.environ['PATH'] += os.pathsep + os.path.abspath(path)
        np.set_printoptions(**self.config['printoptions'])
        exec(self.config.onload, self.user_ns.__dict__)

    def terminate(self):
        if self.control.is_connected():
            self.control.disconnect()
        self.model.set(None)
        self.window.set(None)

    def load_default(self):
        self.configure()
        config = self.config
        filename = self.options['FILE'] or config.load_default
        if filename:
            self.load_model(self.find_model(filename))
        if config.online_control.connect and self.control.can_connect():
            self.control.connect()

    def load_model(self, filename):
        exts = ('.cpymad.yml', '.madx', '.str', '.seq')
        if not any(map(filename.endswith, exts)):
            raise NotImplementedError("Unsupported file format: {}"
                                      .format(filename))
        from madgui.model.madx import Model
        self.model.set(Model.load_file(
            filename, **self.model_args(filename)))

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
        return {}


def subscribe(ns, key, boxed):
    setter = lambda val: setattr(ns, key, val)
    setter(boxed())
    boxed.changed.connect(setter)


def expand_ext(path, *exts):
    for ext in exts:
        if os.path.isfile(path+ext):
            return path+ext
    return path
