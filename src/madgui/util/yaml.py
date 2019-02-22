import os
import sys
from collections import OrderedDict

from importlib_resources import read_binary

import numpy as np
import yaml


# Let's not define bare `load`, `safe` for now:
__all__ = [
    'load_file',
    'safe_load',
    'safe_dump',
    'YAMLError',
    'ParserError',
    'ScannerError',
]

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


if sys.version_info >= (3, 6):
    def safe_load(stream, Loader=SafeLoader):
        return yaml.load(stream, Loader)

else:
    def safe_load(stream, Loader=SafeLoader):
        class OrderedLoader(Loader):
            pass

        def construct_mapping(loader, node):
            loader.flatten_mapping(node)
            return OrderedDict(loader.construct_pairs(node))
        OrderedLoader.add_constructor(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            construct_mapping)
        return yaml.load(stream, OrderedLoader)


def safe_dump(data, stream=None, Dumper=SafeDumper, **kwds):
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
