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

.. graphviz::
    :align: center

    digraph {
        rankdir=LR;
        node [
            shape=rectangle,
            fontsize=10,
            style=rounded,
        ];
        edge [
            fontsize=10
        ];

        // action nodes:
        {
            node [
                shape=diamond,
                width=0.7,
                height=0.5,
                fontsize=9,
                fixedsize=true,
                fillcolor="#eeeeee",
                style=filled,
            ];
            build; test; upload;
        }

        User -> github [label="push"];
        github -> ci [label="notify"];
        ci -> github [label="pull"; style=dashed, color=gray, constraint=false];

        ci -> build -> test;

        test -> coveralls [label="report"];

        test -> upload [
            headlabel="tags   on success",
            labeldistance=3.0,
            labelangle=-40,
        ];

        upload -> pypi [label="release"];
        upload -> github2 [
            headlabel="doc",
            labeldistance=6,
            labelangle=10,
            constraint=false,
        ];

        {rank = same; github2; pypi;}

        {rank = same; ci; build; test; upload;}

        ci [label = "CI"];
        pypi [label = "PyPI"];
        github2 [label = "github"];
    }


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
