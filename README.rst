madgui
======

madgui_ is a Qt5 python GUI for interactive accelerator simulations using MAD-X_.


Requirements
~~~~~~~~~~~~

- **Python >= 3.4**

  *On linux*, I recommend the latest python version you can find.

  *On windows*, I recommend `WinPython 3.4 Qt5`_ (should be about 300MiB in
  size). In particular, you **can not use 64bit python 3.5 and above** on
  windows 10, since there are problems building cpymad for these versions, see
  `hibtc/cpymad#41`_.

- PyQt5_

- cpymad_, in order to work with MAD-X_.

  *On windows*, installing cpymad should be as simple as::

    pip install cpymad

  Otherwise, please refer to cpymad's `installation instructions`_.

.. _WinPython 3.4 Qt5: https://sourceforge.net/projects/winpython/files/WinPython_3.4/3.4.4.6/
.. _hibtc/cpymad#41: https://github.com/hibtc/cpymad/issues/41
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


Configuration
~~~~~~~~~~~~~

The application loads a YAML config file ``madgui.yml`` in the current
directory or the user's home directory.

Example file:

.. code-block:: yaml

    model_path: ../hit_models
    session_file: madgui.session.yml

    onload: |
      from hit_csys.plugin import DllLoader, StubLoader
      frame.add_online_plugin(DllLoader)
      frame.add_online_plugin(StubLoader)

Note that the onload handler can be used to execute user-defined code, import
modules and e.g. add loaders for online control plugins. The API is defined in
the ``madgui.online.api`` module.


Development guidelines
~~~~~~~~~~~~~~~~~~~~~~

**Coding:**

- Try to be consistent with PEP8_ and PEP257_.
- Add `sphinx`_ style docstrings for all modules, classes, functions
- Check regularly for unused imports etc with ``pyflakes madgui``

.. _PEP8: http://www.python.org/dev/peps/pep-0008/
.. _PEP257: http://www.python.org/dev/peps/pep-0257/
.. _`sphinx`: http://sphinx-doc.org/

**Naming:**

- Stick to ``names_with_underscores`` for methods and variable names as
  recommended by PEP8_ (I admit that the code base is currently somewhat
  inconsistent in this regard)
- class names are in ``CamelCase``
- only PyQt class method overrides and their parameters shall be written in
  ``lowerCamelCase``

**Version control:**

Commits should be reversible, independent units if possible. Use descriptive
titles and also add an explaining commit message unless the modification is
trivial. See also: `A Note About Git Commit Messages`_.

.. _`A Note About Git Commit Messages`: http://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html
