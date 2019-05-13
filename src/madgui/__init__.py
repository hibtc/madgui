"""
madgui is a Qt5 python GUI for interactive accelerator simulations using
MAD-X_ via cpymad_.

.. _MAD-X: http://madx.web.cern.ch/madx
.. _cpymad: https://github.com/hibtc/cpymad

To start madgui type at your terminal::

    python -m madgui

or simply::

    madgui

In both cases, the application is started by calling the
:func:`madgui.core.app.main` function.

Note that the ``madgui`` binary may suppress STDOUT on windows. For this
reason the form ``python -m madgui`` may be preferrable if more insight/debug
information is required.

The madgui source code is split into several subpackages under the same root
package:

==================== =========================================================
:mod:`madgui.core`   program entry point and top level program logic
:mod:`madgui.data`   data files needed by madgui, such as icons and config
:mod:`madgui.model`  modules for working with the MAD-X accelerator model
:mod:`madgui.online` interface to the online accelerator control system (ACS)
:mod:`madgui.plot`   utilities for plotting twiss functions and elements
:mod:`madgui.util`   miscellaneous programming utilities used by other modules
:mod:`madgui.widget` definition of windows and widgets
==================== =========================================================
"""

__version__ = '19.5.3'

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

__doc__ += "\n" + __credits__


def get_copyright_notice() -> str:
    """Return madgui license information."""
    from importlib_resources import read_text
    return read_text('madgui.data', 'COPYING.txt')
