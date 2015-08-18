# encoding: utf-8
"""
To start MadGUI type at your terminal:

    python -m madgui

or simply:

    madgui
"""

from __future__ import unicode_literals

__title__ = 'MadGUI'
__summary__ = 'GUI for accelerator simulations using MAD-X.'
__uri__ = 'https://github.com/hibtc/madgui'

__version__ = '0.7.1'

__author__ = 'Thomas Gläßle'
__email__ = 't_glaessle@gmx.de'

__support__ = __email__

__license__ = 'MIT'
__copyright__ = '(C) 2013 - 2015 HIT Betriebs GmbH'

__credits__ = """
MadGUI is developed for HIT Betriebs GmbH.

Created by:

- Thomas Gläßle <t_glaessle@gmx.de>

Special thanks to my supervisors for their help and support:

- Rainer Cee
- Andreas Peters
"""

# Trove classifiers: https://pypi.python.org/pypi?:action=list_classifiers
__classifiers__ = [
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Developers',
    'Intended Audience :: Science/Research',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent',
    'Programming Language :: Python :: 2',
    'Topic :: Scientific/Engineering :: Medical Science Apps.',
    'Topic :: Scientific/Engineering :: Physics',
]

def get_copyright_notice():
    from pkg_resources import resource_string
    return resource_string('madgui', 'LICENSE')
