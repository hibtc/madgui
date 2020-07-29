Welcome to madgui's documentation!
==================================

madgui_ is a Qt5 graphical user interface (GUI) written in Python, designed as
an interactive frontend for MAD-X_. Given a MAD-X input file, madgui_ is
capable of showing the simulated lattice in an interactive window. Up until
now it offers a very comfortable graphical representation of relevant
quantities (e.g. beam envelope, alpha and beta optical functions, emittance,
etc.), which aid to the control of the optimal parameters for the studied
machine or lattice.

.. _madgui: https://github.com/hibtc/madgui
.. _MAD-X: http://cern.ch/mad

The following shows a plot for the Touschek_ example in the madx-examples_
repository, where the Touschek lifetimes and scattering rates are computed for
LHC at injection. The beam envelope [mm] is shown for the first 300m of the
lattice.

.. image:: pictures/LHCInjection.png
   :width: 600
   :alt: Beam envelope [mm] for the first 300m of the injection at LHC

.. _madx-examples: https://github.com/MethodicalAcceleratorDesign/madx-examples
.. _Touschek: https://github.com/MethodicalAcceleratorDesign/madx-examples/tree/master/touschek


Contents
========

.. toctree::
   :maxdepth: 2

   installation
   getting-started
   usrguide/index
   devguide/index
   api/madgui


Links
=====

- `Source code`_
- `Issue tracker`_
- `Latest release`_
- `MAD-X source`_

.. _Source code: https://github.com/hibtc/madgui
.. _Issue tracker: https://github.com/hibtc/madgui/issues
.. _Latest release: https://pypi.org/project/madgui
.. _MAD-X source: https://github.com/MethodicalAcceleratorDesign/MAD-X


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
