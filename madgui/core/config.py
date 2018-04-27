"""
Config serialization utilities.
"""

import os
from importlib_resources import read_binary

from madgui.core.base import Object, Signal
from madgui.util import yaml


__all__ = [
    'load',
]


def get_default_user_config_path():
    """Return the default path of the user config."""
    return os.path.join(os.path.expanduser('~'), '.config', 'madgui', 'config.yml')


def get_default_user_session_path():
    """Return the default path of the user config."""
    return os.path.join(os.path.expanduser('~'), '.config', 'madgui', 'session.yml')


def update_recursive(a, b):
    """Recursively merge two dicts. Updates a."""
    if not isinstance(b, dict):
        return b
    # TODO: allow to control mixin/inheritance behaviour
    for k, v in b.items():
        if k in a and isinstance(a[k], dict):
            a[k] = update_recursive(a[k], v)
        else:
            a[k] = v
    return a


def _read_file(filename):
    try:
        with open(filename, 'rb') as f:
            return f.read()
    except IOError:
        return None

def _loads(text):
    return yaml.safe_load(text) if text else None

def _load_file(path):
    return yaml.safe_load(path and _read_file(path) or '')


def load(*config_files):
    """Read config file and recursively merge it with a base config file."""
    resources = [
        _loads(read_binary('madgui.data', 'config.yml')),   # package default
        _load_file(get_default_user_config_path()),         # user folder
        _load_file('madgui.yml'),                           # current directory
    ]
    resources.extend(map(_load_file, config_files))         # command line
    # NOTE: we deliberately mixin the autosaved session data on lower priority
    # than user defined config files! This allows to always reset specific
    # settings on startup by specifying it in the config file.
    session_file = next(
        (d['session_file'] for d in resources[::-1]
         if d and 'session_file' in d),
        get_default_user_session_path())
    resources.insert(1, _load_file(session_file))
    config = {}
    for merge in resources:
        if merge:
            update_recursive(config, merge)
    config['session_file'] = os.path.abspath(session_file)
    return ConfigSection(config)


class ConfigSection(Object):

    """
    Wrapper class for a config section (dict-like structure in YAML) that
    supports attribute access to config entries, and allows to subscribe for
    updates.

    The ``changed`` signal is is emitted whenever a property in this section
    changes (not in subsections).

    Attribute access is overloaded to return subsections as
    :class:`ConfigSection` and scalar entries as plain values.
    """

    # Returning non-section entries as plain values has the benefit of
    # - less verbose property access (no need for parentheses)
    # - creating fewer `QObject` instances
    # and the following downsides:
    # - less granular changed signal (not needed anyway I guess?)

    changed = Signal()

    def __init__(self, value, parent=None, name=''):
        super().__init__(parent)
        self.setObjectName(name)
        self._value = value
        if isinstance(value, dict):
            self._subsections = {
                name: ConfigSection(value, self, name)
                for name, value in self._value.items()
                if isinstance(value, dict)
            }

    def get(self, name, default=None):
        return self._value.get(name, default)

    def __iter__(self):
        return iter(self._value)

    def __len__(self):
        return len(self._value)

    def __getitem__(self, name):
        return self._value[name]

    def __getattr__(self, name):
        if name not in self._value:
            raise AttributeError(name)
        if name in self._subsections:
            return self._subsections[name]
        return self._value[name]

    def __setitem__(self, name, val):
        if name in self._subsections or isinstance(val, dict):
            raise NotImplementedError('Can only update scalar values!')
        self._value[name] = val
        self.changed.emit()

    def __setattr__(self, name, val):
        if name.startswith('_'):
            super().__setattr__(name, val)
        else:
            self[name] = val

    def __repr__(self):
        return "<{} {}({!r})>".format(
            self.__class__.__name__, self.objectName(), self._value)
