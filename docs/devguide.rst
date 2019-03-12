Developer's guide
=================

As a new developer, please read through this chapter.


Coding conventions
------------------

In general, follow the style of the surrounding code.


**Coding:**

- Use spaces, not tabs! (important for consistent spacing across different
  editor settings and to avoid ``IndentationError``)
- avoid trailing spaces
- Follow PEP8_ and PEP257_.
- Add `sphinx`_ style docstrings for all modules, classes, functions
- Document user-relevant changes in the file ``CHANGES.rst``

.. _PEP8: http://www.python.org/dev/peps/pep-0008/
.. _PEP257: http://www.python.org/dev/peps/pep-0257/
.. _`sphinx`: http://sphinx-doc.org/

**Naming:**

Altough the current code base is not entirely consistent, all new code should
follow these rules:

- class names are in ``CamelCase``
- for method, member and variable names, stick to ``names_with_underscores`` as
  recommended by PEP8_
- PyQt class method overrides and their parameters, as well as child objects
  of widgets are in ``lowerCamelCase``

**Version control:**

Commits should be reversible, independent units if possible. Use descriptive
titles and also add an explaining commit message unless the modification is
trivial. See also: `A Note About Git Commit Messages`_.

.. _`A Note About Git Commit Messages`: http://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html


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


Infrastructure
--------------

Both madgui and cpymad make use of so-called *continuous integration* services
that are triggered whenever a branch is updated on github. When this happens,
the following is done with all supported python versions:

- package is built
- tests are executed
- style checks and consistency checks are performed
- update and upload documentation, if on master
- upload new releases, if a tag was pushed

The following platforms are used:

- `Travis CI`_: executes `linux tests`_ and builds documentation
- `Appveyor CI`_: executes `windows tests`_, currently only for cpymad
- `coveralls`_: test `coverage reports`_ are uploaded here
- `PyPI`_: this is where `new versions`_ for installation via pip are uploaded

The exact build recipes are defined in the files ``.travis.yml`` and
``.appveyor.yml``.

The madgui/cpymad maintainer *must* make an account on both Travis and
Appveyor (login with github should be fine) in order to receive reports about
build and test failures.

Further resources:

- `Travis CI documentation`_
- `Appveyor documentation`_

.. _Travis CI: https://travis-ci.org/
.. _Appveyor CI: https://www.appveyor.com/
.. _coveralls: http://coverage.io/
.. _PyPI: https://pypi.org/

.. _linux tests: https://travis-ci.org/hibtc/madgui
.. _windows tests: https://travis-ci.org/hibtc/cpymad
.. _coverage reports: https://coveralls.io/github/hibtc/cpymad
.. _new versions: https://pypi.org/project/madgui/

.. _Travis CI documentation: https://docs.travis-ci.com/
.. _Appveyor documentation: https://www.appveyor.com/docs/


Creating a new version
----------------------

A new version is defined by creating a dedicated release commit that

- updates the ``__version__`` in ``src/madgui/__init__.py``
- updates ``CHANGES.rst``
- updates dependencies in ``setup.py``
- the commit summary line should follow the format ``Release madgui 19.10.0``

The release commit can be tested by pushing to a special branch:

.. code-block:: bash

    git push -f origin HEAD:test-release

If the build and tests are successful, the release will be uploaded to
test.pypi.org_ from where the wheels can be inspected. Once you are confident
with the commit, you can tag it and upload:

.. code-block:: bash

    git tag VERSION
    git push --tag

If your commit is fine, this will take care of uploading an installable wheel
to PyPI.

Note that madgui version numbers follow a calendaric version scheme
``YY.MM.P``, i.e. two-digit year and month followed by a patch number that can
be increased when releasing multiple versions in the same month. This is well
suited for the application nature of this package with frequent releases.

cpymad version numbers follow a semantic version scheme (semver_) where major
version numbers indicate backwards compatibility. This is better suited for
the library nature of this package.

.. _test.pypi.org: https://test.pypi.org/
.. _semver: https://semver.org/
