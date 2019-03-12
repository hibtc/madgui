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
