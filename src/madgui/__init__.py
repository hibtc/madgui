"""
To start madgui type at your terminal:

    python -m madgui

or simply:

    madgui
"""

__version__ = '19.4.0'

__title__ = 'madgui'
__summary__ = 'GUI for accelerator simulations using MAD-X.'
__uri__ = 'https://github.com/hibtc/madgui'

__credits__ = """
madgui is developed for HIT Betriebs GmbH.

Created by:

- Thomas Gläßle <t_glaessle@gmx.de>

Special thanks to my supervisors for their help and support:

- Rainer Cee
- Andreas Peters
"""


def get_copyright_notice():
    from importlib_resources import read_text
    return read_text('madgui.data', 'COPYING.txt')
