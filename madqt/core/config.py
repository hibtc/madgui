# encoding: utf-8
"""
Config serialization utilities.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import os

from madqt.resource.file import FileResource
from madqt.resource.package import PackageResource
from madqt.core.base import Object, Signal
from madqt.qt import Qt


__all__ = [
    'load',
]


def get_default_user_config_path():
    """Return the default path of the user config."""
    return os.path.join(os.path.expanduser('~'), '.madqt', 'config.yml')


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


def load(*config_files):
    """Read config file and recursively merge it with a base config file."""
    resources = [
        PackageResource('madqt.data', 'config.yml'),    # package default
        FileResource(get_default_user_config_path()),   # user folder
        FileResource('madqt_config.yml'),               # current directory
    ]
    resources.extend([
        FileResource(config_path)                       # command line
        for config_path in config_files
        if config_path
    ])
    config = {}
    for resource in resources:
        try:
            merge = resource.yaml()
        except IOError:
            continue
        update_recursive(config, merge)
    return config


class NumberFormat(Object):
    changed = Signal()
    spinbox = False
    fmtspec = '.4g'
    align = Qt.AlignLeft

# Global format, as singleton, for now:
NumberFormat = NumberFormat()
