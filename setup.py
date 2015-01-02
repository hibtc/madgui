#!/usr/bin/env python
# encoding: utf-8
"""
Installation script for MadGUI.

Usage:
    python setup.py install
"""

# Make sure setuptools is available. NOTE: the try/except hack is required to
# make installation work with pip: If an older version of setuptools is
# already imported, `use_setuptools()` will just exit the current process.
try:
    import pkg_resources
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()

from setuptools import setup
from distutils.util import convert_path


def exec_file(path):
    """Execute a python file and return the `globals` dictionary."""
    namespace = {}
    with open(convert_path(path)) as f:
        exec(f.read(), namespace, namespace)
    return namespace


meta = exec_file('madgui/__init__.py')


setup(
    name='madgui',
    version=meta['__version__'],
    description=meta['__summary__'],
    long_description=open('README.rst').read(),
    author=meta['__author__'],
    author_email=meta['__email__'],
    url=meta['__uri__'],
    packages=[
        'madgui',
        'madgui.component',
        'madgui.core',
        'madgui.resource',
        'madgui.util',
        'madgui.widget',
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Topic :: Scientific/Engineering :: Medical Science Apps.',
        'Topic :: Scientific/Engineering :: Physics',
    ],
    license=meta['__license__'],
    test_suite='nose.collector',
    install_requires=[
        'cpymad==0.10.0',
        'docopt',
        'matplotlib',
        'numpy',
        'pydicti>=0.0.4',
        'PyYAML',
        'Unum>=4.0',
        'wxPython>=2.8',
    ],
    entry_points="""
        [gui_scripts]
        madgui = madgui.core.app:App.main

        [madgui.core.app.init]
        mainframe = madgui.widget.notebook:NotebookFrame

        [madgui.widget.figure.init]
        matchtool = madgui.component.matchtool:MatchTool
        selecttool = madgui.component.selecttool:SelectTool
        comparetool = madgui.component.comparetool:CompareTool
        statusbar = madgui.component.lineview:UpdateStatusBar.create
        drawelements = madgui.component.lineview:DrawLineElements.create

        [madgui.component.matching.start]
        drawconstraints = madgui.component.lineview:DrawConstraints

        [madgui.widget.notebook.menu]
        openmodel = madgui.component.openmodel:OpenModelDlg.connect_menu
        plainopen = madgui.component.plainopen:connect_menu
        changetwiss = madgui.component.changetwiss:TwissDialog.connect_menu
        beamdlg = madgui.component.beamdlg:BeamDialog.connect_menu
        lineview = madgui.component.lineview:EnvView.connect_menu
        xyview = madgui.component.lineview:XYView.connect_menu
        about = madgui.component.about:connect_menu
    """,
    package_data={
        'madgui': [
            'config.yml',
            'resource/*.xpm',
            'LICENSE',
        ]
    }
)
