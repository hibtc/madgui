"""
Utility functions for use with QFileDialog.
"""


from __future__ import absolute_import
from __future__ import unicode_literals


__all__ = [
    'make_filter',
]


def make_filter(wildcards):
    """
    Create wildcard string from multiple wildcard tuples.

    For example:

        >>> make_filter([
        ...     ('All files', '*'),
        ...     ('Text files', '*.txt', '*.log'),
        ... ])
        All files (*);;Text files (*.txt *.log)
    """
    return ";;".join("{0} ({1})".format(w[0], " ".join(w[1:]))
                     for w in wildcards)
