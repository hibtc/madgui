"""
Utilities for loading and writing YAML_ documents. We currently use YAML for
config files, session data and various data exports.

The functions here are merely thin wrappers on top of the PyYAML API. They
mainly add these features:

- the ``load`` functions are order preserving, i.e. they return dicts that when
  iterated yield elements in the same order as written in the YAML document
- the ``save`` family of functions handle serialization of :class:`OrderedDict`
  and several numpy number types that would otherwise raise an error.
- :func:`load_file` and :func:`save_file` allow to directly provide a filename
  rather than having to pass a stream.
- the :func:`save_file` function ensures that an existing file at the same
  location will only be overwritten if the data can be serialized without
  error.
- :func:`save_file` creates directories as needed

.. _YAML: https://en.wikipedia.org/wiki/YAML
"""

# Let's not define bare `load`, `safe` for now:
__all__ = [
    'load_file',
    'safe_load',
    'safe_dump',
    'YAMLError',
    'ParserError',
    'ScannerError',
]

import os
from collections import OrderedDict

from importlib_resources import read_binary

import numpy as np
import yaml


# For speed:
SafeLoader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
SafeDumper = getattr(yaml, 'CSafeDumper', yaml.SafeDumper)

YAMLError = yaml.error.YAMLError
ParserError = yaml.parser.ParserError
ScannerError = yaml.scanner.ScannerError


def load_file(filename):
    """Load yaml document from filename."""
    with open(filename, 'rb') as f:
        return safe_load(f)


def save_file(filename, data, **kwargs):
    """
    Write yaml document to file. This creates parent folders where necessary.
    Note that this function deliberately serializes the data *before* opening
    the file. This prevents accidentally truncating a useful file or leaving
    the output in an inconsistent state if an error occurs during
    serialization.
    """
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    kwargs.setdefault('default_flow_style', False)
    # Always serialize data to string first, before opening the file! If the
    # serialization raises an exception, we will at least not accidentally
    # have truncated an existing file!
    text = safe_dump(data, **kwargs)
    with open(filename, 'wt') as f:
        f.write(text)


def load_resource(package, resource):
    """Load yaml document from package resource."""
    return safe_load(read_binary(package, resource))


def safe_load(stream, Loader=SafeLoader):
    """Load YAML document from stream, returns dictionaries in the
    written order within the YAML document."""
    return yaml.load(stream, Loader)


def safe_dump(data, stream=None, Dumper=SafeDumper, **kwds):
    """Saves YAML document to stream (or returns as string). This function
    takes care to correctly serialize ``OrderedDict``, as well as several
    numpy number types, which would otherwise lead to errors.

    Note that it is easy to accidentally have some of these types in your data
    if not taking extreme care. For example, if you retrieve an array element
    fron numpy using ``array[i]``, you will not get a python float or int, but
    a numpy specific datatype.
    """
    class OrderedDumper(Dumper):
        pass

    def _dict_representer(dumper, data):
        return dumper.represent_mapping(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            data.items())
    OrderedDumper.add_representer(OrderedDict, _dict_representer)
    OrderedDumper.add_representer(np.bool, Dumper.represent_bool)
    OrderedDumper.add_representer(np.int32, Dumper.represent_int)
    OrderedDumper.add_representer(np.int64, Dumper.represent_int)
    OrderedDumper.add_representer(np.float32, Dumper.represent_float)
    OrderedDumper.add_representer(np.float64, Dumper.represent_float)
    return yaml.dump(data, stream, OrderedDumper, **kwds)
