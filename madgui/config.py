# encoding: utf-8
"""
Config serialization utilities.
"""

# force new style imports
from __future__ import absolute_import

# standard library
import os

# 3rd party dependencies
import yaml

# exported symbols
__all__ = ['load_config']


def default_base_config_path():
    """Return the default path of the base config."""
    return os.path.join(os.path.dirname(__file__), 'config.yml')


def default_user_config_path():
    """Return the default path of the user config."""
    return os.path.join(os.path.expanduser('~'), '.madgui', 'config.yml')


def _load_file(path):
    """Load a yaml file."""
    with open(path) as f:
        return yaml.safe_load(f)


def recursive_merge(a, b):
    """Recursively merge two dicts. Updates a."""
    if not isinstance(b, dict):
        return b
    for k, v in b.items():
        if k in a and isinstance(a[k], dict):
            a[k] = recursive_merge(a[k], v)
        else:
            a[k] = v
    return a


def load_config(cls, path_user=None, path_base=None):
    """Read config file and recursively merge it with a base config file."""
    base_config = _load_file(path_base or default_base_config_path())
    user_config = {}
    if path_user:
        user_config = _load_file(path_user)
    else:
        try:
            user_config = _load_file(default_user_config_path())
        except IOError:
            pass
    return recursive_merge(base_config, user_config)
