MadQt
=====

MadQt_ is a python GUI for interactive accelerator simulations using MAD-X_
or `Bmad/tao`_.


Dependencies
~~~~~~~~~~~~

Needs to be built manually:

- cpymad_ (for MAD-X_ models, see `installation instructions`_)
- pytao_ (for `Bmad/tao`_ models)
- minrpc_ (common dependency of both cpymad and pytao)

These are likely to be available in your system repositories:

- PyQt5_
- matplotlib_
- numpy_

These can easily be installed via PyPI (``pip install ...``) if unavailable
in your repositories:

- docopt_
- Pint_ == 0.6
- PyYAML_
- six_
- docutils_
- ipython_
- qtconsole_
- minrpc_

.. _installation instructions: http://hibtc.github.io/cpymad/installation/index.html
.. _MAD-X: http://madx.web.cern.ch/madx
.. _Bmad/tao: http://www.lepp.cornell.edu/~dcs/bmad/
.. _cpymad: https://github.com/hibtc/cpymad
.. _pytao: https://github.com/hibtc/pytao
.. _minrpc: https://pypi.python.org/pypi/minrpc
.. _PyQt5: https://riverbankcomputing.com/software/pyqt/intro
.. _matplotlib: http://matplotlib.org/
.. _numpy: http://www.numpy.org
.. _docopt: https://pypi.python.org/pypi/docopt
.. _Pint: http://pint.readthedocs.org/
.. _PyYAML: https://pypi.python.org/pypi/PyYAML
.. _six: https://pypi.python.org/pypi/six
.. _docutils: https://pypi.python.org/pypi/docutils
.. _ipython: https://pypi.python.org/pypi/ipython
.. _qtconsole: https://pypi.python.org/pypi/qtconsole


Installation
~~~~~~~~~~~~

After installing the dependencies, open a terminal in the project folder and
type::

    python setup.py install


Usage
~~~~~

Now, you should be able to start MadQt with the command::

    madqt

or::

    python -m madqt


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

**Naming:**

- Stick to ``names_with_underscores`` for methods and variable names as
  mandated by PEP8_ (I admit that the code base is currently very
  inconsistent in this regard)
- class names are in ``CamelCase``
- only PyQt class method overrides and their parameters shall be written in
  ``lowerCamelCase``

**Version control:**

Commits should be reversible, independent units if possible. Use descriptive
titles and also add an explaining commit message unless the modification is
trivial. See also: `A Note About Git Commit Messages`_.

.. _`A Note About Git Commit Messages`: http://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html
