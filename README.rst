madgui
======

madgui is a Qt5 python GUI for interactive accelerator simulations using MAD-X_.


Requirements
~~~~~~~~~~~~

- **Python >= 3.4** (higher is better, except on windows, see `hibtc/cpymad#41`_!)

- PyQt5_

- cpymad_, see cpymad's `installation instructions`_.

.. _WinPython 3.4 Qt5: https://sourceforge.net/projects/winpython/files/WinPython_3.4/3.4.4.6/
.. _hibtc/cpymad#41: https://github.com/hibtc/cpymad/issues/41
.. _installation instructions: http://hibtc.github.io/cpymad/installation/index.html
.. _MAD-X: http://madx.web.cern.ch/madx
.. _cpymad: https://github.com/hibtc/cpymad
.. _PyQt5: https://riverbankcomputing.com/software/pyqt/intro


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
      backend: 'hit_csys.plugin:TestBackend'
    onload: |
      code to execute on startup


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

Altough the current code base is not entirely consistent, all new code should
follow these rules:

- class names are in ``CamelCase``
- for method, member and variable names, stick to ``names_with_underscores`` as
  recommended by PEP8_
- only PyQt class method overrides and their parameters shall be written in
  ``lowerCamelCase``

**Version control:**

Commits should be reversible, independent units if possible. Use descriptive
titles and also add an explaining commit message unless the modification is
trivial. See also: `A Note About Git Commit Messages`_.

.. _`A Note About Git Commit Messages`: http://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html
