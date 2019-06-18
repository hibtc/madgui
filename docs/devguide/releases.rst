Creating a new version
----------------------

In order to create a new version the following should be done:

- update ``__version__`` in ``src/madgui/__init__.py``
- update ``CHANGES.rst`` by looking at the commit log
- update dependencies in ``setup.py`` (if necessary)
- commit these changes in a single commit with the title
  ``Release madgui YY.M.P``, e.g. ``Release madgui 19.6.0``
- test the release by pushing to the special ``test-release`` branch::

    git push -f origin HEAD:test-release

  If the build and tests are successful, the release will be uploaded to
  test.pypi.org_ from where the wheels can be inspected.

- Once you are confident with the commit, you can tag it and upload::

    git tag YY.M.P
    git push
    git push --tag

  If your commit is fine, this will take care of uploading an installable
  wheel to PyPI. The tests and documentation will be build for any commit, but
  releases will only be uploaded when a tag is pushed.
- Once the madgui release has appeared on PyPI, you can proceed to build an
  installer for offline installation using the madgui-installer_ repository,
  see `Creating an offline installer`_.

.. graphviz::
    :align: center

    digraph {
        newrank=true;

        // fake levels for structuring:
        subgraph {
            node [
                shape=none,
                fontcolor=gray,
                label="",
                height=0,
                width=0,
                fixedsize=true
            ];
            edge [color=none];
            l0 -> l1 -> l2 -> l3 -> l4 -> l5 -> l6 -> l7 -> l8 -> l9 -> l10;
            label="";
            color=none;
        }

        subgraph cluster_0 {
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
                tag; tag2 [label="tag"];
                push; push2 [label="push"];
                wait;
            }

            {
                node [ shape=rectangle ];
                madgui; installer;
            }


            madgui -> tag -> push -> wait;
            wait -> installer -> tag2 -> push2;

            label="User";
            color=gray;

            {
                node [shape=none, label=""];
                U9;
            }
        }


        subgraph cluster_1 {
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
                notify; notify2 [label="notify"];
            }


            notify;
            notify2;

            {
                node [shape=none, label=""];
                G0;
                G9;
            }

            {
                node [shape=point, label="", height=0, width=0];
                G5;
            }

            label="Github";
            color=gray;
        };

        subgraph cluster_2 {
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
                build; build2 [label="build"];
                upload; upload2 [label="upload"];
                test; 
            }

            build -> test -> upload;
            build2 -> upload2;

            {
                node [shape=none, label=""];
                C0;
            }

            {
                node [shape=point, label="", height=0, width=0];
                C5;
            }

            label="CI";
            color=gray;
        }

        subgraph cluster_3 {
            {
                node [ shape=rectangle ];
                pypi; github;
            }

            {
                node [shape=none, label=""];
                W0;
            }

            {
                node [shape=point, label="", height=0, width=0];
                W5; W8;
            }

            pypi -> W5 -> W8 [arrowhead=none];

            label="Result";
            color=gray;
        }

        push -> notify -> build [constraint=false];
        push2 -> notify2 -> build2 [constraint=false];

        upload -> pypi [constraint=false];
        upload2 -> github [constraint=false];

        W8 -> build2 [constraint=false];

        // For some reason, we need C5/G5 as intermediate nodes to avoid an
        // error in graphviz (triangulation failed):
        W5 -> C5 -> G5 [constraint=false, dir=none];
        G5 -> wait [constraint=false];

        {rank = same; l0; madgui; G0; C0; W0;}
        {rank = same; l1; tag;}
        {rank = same; l2; push; notify; build;}
        {rank = same; l3; test;}
        {rank = same; l4; upload; pypi;}
        {rank = same; l5; wait; G5; C5; W5;}

        {rank = same; l6; installer;}
        {rank = same; l7; tag2;}
        {rank = same; l8; push2; notify2; build2; W8;}
        {rank = same; l9; upload2; github; U9; G9;}

    }


**Important:** It is important to subscribe to updates on the appveyor_ and
travis_ continuous integration services (build farms) that are used to create
and test releases, in order to be notified when and why builds or tests start
failing. You can use the github account to login on both platforms.

.. _test.pypi.org: https://test.pypi.org/
.. _travis: https://travis-ci.org/hibtc/madgui
.. _appveyor: https://ci.appveyor.com/project/coldfix/madgui-installer
.. _madgui-installer: https://github.com/hibtc/madgui-installer


Version numbers
```````````````

Note that madgui version numbers follow a calendaric version scheme (calver_)
``YY.M.P``, i.e. two-digit year, one-digit month followed by a patch number
starting at ``0`` that can be increased when releasing multiple versions in
the same month. This is well suited for the application nature of this package
with frequent releases.

cpymad version numbers follow a semantic version scheme (semver_) where major
version numbers indicate backwards compatibility. This is better suited for
the library nature of this package.

.. _calver: https://calver.org/
.. _semver: https://semver.org/


Creating an offline installer
`````````````````````````````

- Clone the madgui-installer_ repository::

    git clone git@github.com:hibtc/madgui-installer

- Update ``requirements.txt`` with the new madgui version (and possibly other
  dependencies). These versions must have been uploaded to PyPI in order to be
  used by this repository.
- Commit the changes.
- Tag the commit with the madgui version: ``git tag YY.M.P``
- Push the commit and tag::

    git push --tag
    git push

- Wait for appveyor_ to finish the build
- Download the new installer from the `releases page`_

.. _releases page: https://github.com/hibtc/madgui-installer/releases


If something goes wrong
```````````````````````

If you notice a bug or an error in an already uploaded version, fix the
problem and then issue a new release.

If the travis or appveyor builds failed for an unrelated reason (e.g.
downtime on some dependent server), go to the travis/appveyor build page and
restart the build.

If you have pushed a tag that failed to build, it is possible to remove the
tag from github using the syntax::

    git push origin :YY.M.P

(However, don't do this if the version was already released)
