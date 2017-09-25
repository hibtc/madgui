# encoding: utf-8
"""
To start MadQt type at your terminal:

    python -m madqt

or simply:

    madqt
"""

from __future__ import unicode_literals

__title__ = 'MadQt'
__summary__ = 'GUI for accelerator simulations using MAD-X.'
__uri__ = 'https://github.com/hibtc/madqt'

__version__ = '0.0.0'

__author__ = 'Thomas Gläßle'
__email__ = 't_glaessle@gmx.de'

__support__ = __email__

__license__ = 'GPLv3+'
__copyright__ = 'Copyright 2016 HIT Betriebs GmbH'

__credits__ = """
MadQt is developed for HIT Betriebs GmbH.

Created by:

- Thomas Gläßle <t_glaessle@gmx.de>

Special thanks to my supervisors for their help and support:

- Rainer Cee
- Andreas Peters
"""

# Trove classifiers: https://pypi.python.org/pypi?:action=list_classifiers
__classifiers__ = [
    'Development Status :: 3 - Alpha',
    'Environment :: X11 Applications :: Qt',
    'Intended Audience :: Developers',
    'Intended Audience :: Science/Research',
    'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
    'Operating System :: OS Independent',
    'Programming Language :: Python :: 2',
    'Programming Language :: Python :: 3',
    'Topic :: Scientific/Engineering :: Medical Science Apps.',
    'Topic :: Scientific/Engineering :: Physics',
]

# importing pkg_resources is pretty expensive, so don't do it by default:
def get_copyright_notice():
    from pkg_resources import resource_string
    return resource_string('madqt', 'COPYING.txt')
