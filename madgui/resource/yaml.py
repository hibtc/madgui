import sys
from collections import OrderedDict

import yaml


# Let's not define bare `load`, `safe` for now:
__all__ = [
    'safe_load',
    'safe_dump',
]

# For speed:
SafeLoader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
SafeDumper = getattr(yaml, 'CSafeDumper', yaml.SafeDumper)


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
    return yaml.dump(data, stream, OrderedDumper, **kwds)
