"""
Config serialization utilities.
"""

import os
from importlib_resources import read_binary

from madgui.core.base import Object, Signal
from madgui.util import yaml
from madgui.qt import Qt


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


def load(*config_files):
    """Read config file and recursively merge it with a base config file."""
    # NOTE: we deliberately mixin the autosaved session data on lower priority
    # than user defined config files! This allows to always reset specific
    # settings on startup by specifying it in the config file.
    resources = [
        read_binary('madgui.data', 'config.yml'),   # package default
        _read_file(get_default_user_session_path()),# user folder
        _read_file(get_default_user_config_path()), # user folder
        _read_file('madgui.yml'),                   # current directory
    ]
    resources.extend([
        _read_file(config_path)                       # command line
        for config_path in config_files
        if config_path
    ])
    config = {}
    for resource in resources:
        if resource:
            merge = yaml.safe_load(resource)
            update_recursive(config, merge)
    return config


class NumberFormat(Object):
    changed = Signal()
    spinbox = True
    fmtspec = '.4g'
    align = Qt.AlignRight

# Global format, as singleton, for now:
NumberFormat = NumberFormat()
