madgui
======

madgui_ is a Qt5 python GUI for interactive accelerator simulations using MAD-X_.


Requirements
~~~~~~~~~~~~

- **Python >= 3.3**

  *On linux*, I recommend the latest python version you can find.

  *On windows*, I strongly recommend `WinPython 3.4`_ (pick an installer with
  Qt5 suffix, should be about 300MiB in size). In particular, you **can not
  use python 3.5 and above**, since there are problems building cpymad for
  these versions, see `hibtc/cpymad#32`_.

- PyQt5_, should be installed using the official installer or your
  distributions package manager.

- cpymad_, in order to work with MAD-X_.

  *On windows*, installing cpymad for python 3.3 or 3.4 should be as simple as::

    pip install cpymad

  Otherwise, please refer to cpymad's `installation instructions`_.

.. _WinPython 3.4: https://sourceforge.net/projects/winpython/files/WinPython_3.4/
.. _hibtc/cpymad#32: https://github.com/hibtc/cpymad/issues/32
.. _installation instructions: http://hibtc.github.io/cpymad/installation/index.html
.. _MAD-X: http://madx.web.cern.ch/madx
.. _cpymad: https://github.com/hibtc/cpymad
.. _PyQt5: https://riverbankcomputing.com/software/pyqt/intro


Installation
~~~~~~~~~~~~

You are now ready to install madgui. Type::

    pip install madgui

Or, in order to install from the local checkout::

    python setup.py install

If you intend to make changes to the madgui code and want to try the effects
immediately, use::

    python setup.py develop


Usage
~~~~~

Now, you should be able to start madgui with the command::

    madgui

or::

    python -m madgui

If you are on windows, and nothing happens, you can start madgui manually as
follows, which may provide you with more error information::

    python -c "from madgui.core.app import main; main()"


Development guidelines
~~~~~~~~~~~~~~~~~~~~~~

**Coding:**

- Try to be consistent with PEP8_ and PEP257_.
- Add `unit tests`_ for all non-trivial functionality.
- `Dependency injection`_ is a great pattern to keep modules testable.
- Prefer `composition over inheritance`_
- Add `sphinx`_ style docstrings for all modules, classes, functions
- Check regularly for unused imports etc with ``pyflakes madgui``

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
