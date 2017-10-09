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


def get_long_description():
    """Compose a long description for PyPI."""
    long_description = None
    try:
        long_description = read_file('README.rst').decode('utf-8')
        long_description += '\n' + read_file('COPYING.rst').decode('utf-8')
        long_description += '\n' + read_file('CHANGES.rst').decode('utf-8')
    except (IOError, UnicodeDecodeError):
        pass
    return long_description


def main():
    """Execute setup."""
    long_description = get_long_description()
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
            'madqt.correct',
            'madqt.data',
            'madqt.engine',
            'madqt.online',
            'madqt.plot',
            'madqt.resource',
            'madqt.util',
            'madqt.widget',
        ],
        install_requires=[
            'docopt',           # command line parsing
            'matplotlib',
            'numpy',
            'PyYAML',           # config/model files
            'Pint==0.6',
            'docutils',         # about dialogs
            'six>=1.10.0',      # py2/3 compatibility
            # inprocess python shell:
            'ipython',
            'qtconsole',
            # 'PyQt4',
        ],
        # Make sure to always have at least one of these installed:
        extras_require={
            'madx': ['cpymad>=0.17.1'],
            'bmad': ['pytao'],
        },
        entry_points="""
            [gui_scripts]
            madqt = madqt.core.app:main
        """,
        package_data={
            'madqt': [
                'COPYING.txt',
                'data/*.txt',
                'data/*.yml',
                'data/*.xpm',
                'data/*.css',
                'engine/*.yml',
            ]
        }
    )


if __name__ == '__main__':
    main()
