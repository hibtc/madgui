#!/usr/bin/env python
# encoding: utf-8
"""
Installation script for MadQt.

Usage:
    python setup.py install
"""

from setuptools import setup
from distutils.util import convert_path


def read_file(path):
    """Read a file in binary mode."""
    with open(convert_path(path), 'rb') as f:
        return f.read()


def exec_file(path):
    """Execute a python file and return the `globals` dictionary."""
    namespace = {}
    exec(read_file(path), namespace, namespace)
    return namespace


def main():
    """Execute setup."""
    long_description = read_file('README.rst').decode('utf-8')
    meta = exec_file('madqt/__init__.py')
    setup(
        name='MadQt',
        version=meta['__version__'],
        description=meta['__summary__'],
        long_description=long_description,
        author=meta['__author__'],
        author_email=meta['__email__'],
        url=meta['__uri__'],
        license=meta['__license__'],
        classifiers=meta['__classifiers__'],
        packages=[
            'madqt',
            'madqt.core',
            'madqt.data',
            'madqt.engine',
            'madqt.resource',
            'madqt.util',
        ],
        install_requires=[
            'cpymad>=0.14.1',
            'docopt',
            'matplotlib',
            'numpy',
            'pydicti>=0.0.5',
            'PyYAML',
            'Pint==0.6',
            'docutils',
            'six>=1.10.0',
            # 'PyQt4',
        ],
        entry_points="""
            [gui_scripts]
            madqt = madqt.core.app:main
        """,
        package_data={
            'madqt': [
                'LICENSE',
            ]
        }
    )


if __name__ == '__main__':
    main()
