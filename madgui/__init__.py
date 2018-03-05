"""
To start madgui type at your terminal:

    python -m madgui

or simply:

    madgui
"""

__title__ = 'madgui'
__summary__ = 'GUI for accelerator simulations using MAD-X.'
__uri__ = 'https://github.com/hibtc/madgui'

__version__ = '1.7.2'

__author__ = 'Thomas Gläßle'
__email__ = 't_glaessle@gmx.de'

__support__ = __email__

__license__ = 'GPLv3+'
__copyright__ = 'Copyright 2016-2018 HIT Betriebs GmbH'

__credits__ = """
madgui is developed for HIT Betriebs GmbH.

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
    'Programming Language :: Python :: 3',
    'Topic :: Scientific/Engineering :: Medical Science Apps.',
    'Topic :: Scientific/Engineering :: Physics',
]

# importing pkg_resources is pretty expensive, so don't do it by default:
def get_copyright_notice():
    from pkg_resources import resource_string
    return resource_string('madgui', 'COPYING.txt').decode('utf-8')
