"""
Config serialization utilities.
"""

__all__ = [
    'load',
    'ConfigSection',
    'user_home',
    'user_config_path',
    'user_session_path',
]

import os

from madgui.util.signal import Signal
from madgui.util import yaml


user_home = os.path.expanduser('~')
user_config_path = os.path.join(user_home, '.config', 'madgui', 'config.yml')
user_session_path = os.path.join(user_home, '.config', 'madgui', 'session.yml')


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


def _load_file(path):
    try:
        return yaml.load_file(path or '')
    except FileNotFoundError:
        return ''


def load(*config_files, isolated=False):
    """Read config file and recursively merge it with a base config file."""
    resources = [
        yaml.load_resource('madgui.data', 'config.yml'),    # package default
    ] + ([] if isolated else [
        _load_file(user_config_path),                       # user folder
        _load_file('madgui.yml'),                           # current directory
    ])
    resources.extend(map(_load_file, config_files))         # command line
    # NOTE: we deliberately mixin the autosaved session data on lower priority
    # than user defined config files! This allows to always reset specific
    # settings on startup by specifying it in the config file.
    session_file = next(
        (d['session_file'] for d in resources[::-1]
         if d and 'session_file' in d),
        user_session_path)
    resources.insert(1, _load_file(session_file))
    config = {}
    for merge in resources:
        if merge:
            update_recursive(config, merge)
    config['session_file'] = os.path.abspath(session_file)
    return ConfigSection(config)


class ConfigSection:

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
        self._name = name
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
            self.__class__.__name__, self._name, self._value)
