Related projects
----------------

This is a short overview over the components involved in madgui development:

- madgui_: main application repository that contains GUI code and orchestrates
  the interaction between different parts
- cpymad_: python binding for MAD-X_. It allows to start, access and control
  the MAD-X interpreter from python.
- MAD-X_: accelerator simulation code developed by CERN, used for underlying
  computations. Note that although "open source" it is **not** "free software".
- hit_acs_: python binding for the hit accelerator control system,
  specifically the ``BeamOptikDLL.dll``. This component is required for online
  access at HIT. It is possible to replace this component with another package
  with similar API to facilitate access to other control systems.
- hit_models_: contains the MAD-X model definitions for the HIT beam lines
- madgui-installer_: scripts to create an offline installer with all
  dependencies for usage on the control system PCs (which don't have internet
  and therefore can't download dependencies automatically)
- PyQt5_: GUI framework.

Further resources:

- `the MAD-X user's guide`_ is an essential resource and a **must read**
- `cpymad documentation`_
- `Qt5 documentation`_ use this as reference for developing with Qt. It is
  often much better and complete than PyQt-specific references. The PyQt API
  is essentially the same just with C++ translated to python.

.. _madgui: https://github.com/hibtc/madgui
.. _cpymad: https://github.com/hibtc/cpymad
.. _MAD-X: https://github.com/MethodicalAcceleratorDesign/MAD-X
.. _hit_acs: https://github.com/hibtc/hit_acs
.. _hit_models: https://github.com/hibtc/hit_models
.. _madgui-installer: https://github.com/hibtc/madgui-installer
.. _PyQt5: http://pyqt.sourceforge.net/Docs/PyQt5/installation.html

.. _the MAD-X user's guide: http://mad.web.cern.ch/mad/documentation.html
.. _Qt5 documentation: https://doc.qt.io/qt-5/
.. _cpymad documentation: https://hibtc.github.io/cpymad/
