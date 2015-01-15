MadGUI
------

Description
~~~~~~~~~~~

MadGUI is a python GUI for accelerator simulations using MAD-X_. Currently,
it is rather basic, since it is still under heavy development.


Dependencies
~~~~~~~~~~~~

Needs to be built manually (see `installation instructions`_):

- MAD-X_ as a library (``.dll``, ``.lib`` or ``.so``)
- cpymad_

These are likely to be available in your system repositories:

- wxPython_
- matplotlib_
- numpy_

These can easily be installed via PyPI (``pip install ...``) if unavailable
in your repositories:

- docopt_
- Unum_
- pydicti_
- PyYAML_

.. _installation instructions: http://hibtc.github.io/cpymad/installation/index.html
.. _MAD-X: http://madx.web.cern.ch/madx
.. _cpymad: https://github.com/hibtc/cpymad
.. _wxPython: http://www.wxpython.org/
.. _matplotlib: http://matplotlib.org/
.. _numpy: http://www.numpy.org
.. _docopt: https://pypi.python.org/pypi/docopt
.. _Unum: https://pypi.python.org/pypi/Unum
.. _pydicti: https://github.com/coldfix/pydicti
.. _PyYAML: https://pypi.python.org/pypi/PyYAML


Development guidelines
~~~~~~~~~~~~~~~~~~~~~~

**Coding:**

- Try to be consistent with PEP8_ and PEP257_.
- Add `unit tests`_ for all non-trivial functionality.
- `Dependency injection`_ is a great pattern to keep modules testable.
- Prefer `composition over inheritance`_
- Add `sphinx`_ style docstrings for all modules, classes, functions

.. _PEP8: http://www.python.org/dev/peps/pep-0008/
.. _PEP257: http://www.python.org/dev/peps/pep-0257/
.. _`unit tests`: http://docs.python.org/2/library/unittest.html
.. _`Dependency injection`: http://www.youtube.com/watch?v=RlfLCWKxHJ0
.. _`composition over inheritance`: https://www.youtube.com/watch?v=Tedt47e9qsQ
.. _`sphinx`: http://sphinx-doc.org/

**Version control:**

Commits should be reversible, independent units if possible. Use descriptive
titles and also add an explaining commit message unless the modification is
trivial. See also: `A Note About Git Commit Messages`_.

.. _`A Note About Git Commit Messages`: http://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html

