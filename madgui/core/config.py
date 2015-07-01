# encoding: utf-8
"""
Config serialization utilities.
"""

# force new style imports
from __future__ import absolute_import

# standard library
import os
from pkg_resources import resource_string

# 3rd party dependencies
import yaml

# exported symbols
__all__ = [
    'load_config',
]


def get_base_config():
    """Return the builtin base configuration."""
    return yaml.safe_load(resource_string('madgui', 'config.yml'))


def get_default_user_config_path():
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


def existing_path(path):
    return path if os.path.exists(path) else None


def load_config(config_path=None):
    """Read config file and recursively merge it with a base config file."""
    base_config = get_base_config()
    config_path = (config_path or
                   existing_path('madgui_config.yml') or
                   existing_path(get_default_user_config_path()))
    if config_path:
        recursive_merge(base_config, _load_file(config_path))
    return base_config
