madgui
======

madgui is a Qt5 python GUI for interactive accelerator simulations using
MAD-X_ via cpymad_. It currently runs on python 3.4 and above, but higher
python versions may be required in the near future.

.. _MAD-X: http://madx.web.cern.ch/madx
.. _cpymad: https://github.com/hibtc/cpymad


Installation
~~~~~~~~~~~~

.. code-block:: bash

    pip install madgui


Usage
~~~~~

Now, you should be able to start madgui with the command::

    madgui

Optionally, madgui can take a filename for a madx/model file::

    madgui /path/to/model.madx

Note that madgui is currently only suited for relatively small sequences, on
the scale of few hundred elements at the most. Don't say I didn't warn you if
you use it with the LHC;)


Configuration
~~~~~~~~~~~~~

The application loads a YAML config file ``madgui.yml`` in the current
directory or the user's home directory.

Example file:

.. code-block:: yaml

    model_path: ../hit_models
    session_file: madgui.session.yml
    online_control:
      connect: true
      backend: 'hit_acs.plugin:TestACS'
    onload: |
      code to execute on startup


Development guidelines
~~~~~~~~~~~~~~~~~~~~~~

See `Developer's Guide`_.

.. _Developer's Guide: https://hibtc.github.io/madgui/devguide
