.. highlight:: bash

Development setup for madgui
============================

This section describes how to setup a development environment for madgui. This
section is relevant only for those who are planning to modify the madgui
source code or check out an unreleased version from github.

If you are behind a firewall or proxy like at HIT, please take a look at the
proxy-settings_ documentation first and then come back here.

.. _proxy-settings: ./proxy


Environment
~~~~~~~~~~~

When developing a python application or package, it is best to have a separate
environment in which the application is installed. This prevents version
conflicts with other applications and makes it clearer what dependencies the
program has.

If you already have experience with venvs or virtualenvs and
virtualenvwrapper, you can use these. **Otherwise,** I highly recommend using
either Miniconda_ or Anaconda_. Personally, I use miniconda on windows.

**conda:** In the following we give a quick introduction on how to work with
conda environments.

.. _Miniconda: https://docs.conda.io/en/latest/miniconda.html
.. _Anaconda: https://www.anaconda.com/distribution/#download-section

First, create a virtual environment named *madgui* with python 3.7 in it::

    conda create -n madgui python=3.7

And activate the virtual environment with::

    conda activate madgui

With older versions of conda, this command may be different and you may have
to write either ``activate madgui`` or ``source activate madgui``.

We will use *pip* as the main python package installation tool in the
following. On recent conda versions, pip should be preinstalled in the
environment. If this is not the case, install as follows::

    conda install pip


Installation
~~~~~~~~~~~~

madgui depends on cpymad_ which in turn requires MAD-X_ and cython_ to build.
As long as you are not planning to modify cpymad code, it is much easier and
in fact recommended to just install cpymad using pip at this point::

    pip install cpymad

Once you decide that you do need to modify cpymad code, please refer to
cpymad's `installation instructions`_ which explains how to setup cpymad in a
development environment.

.. _cpymad: https://hibtc.github.io/cpymad/installation/windows.html
.. _MAD-X: http://mad.web.cern.ch/mad/
.. _cython: https://cython.org/
.. _installation instructions: https://hibtc.github.io/cpymad/installation

At this point, I assume you have installed cpymad. To check that the cpymad
installation is working, run the following line in the terminal::

    python -c "import cpymad.libmadx as l; l.start()"

A banner like this should appear::

    ++++++++++++++++++++++++++++++++++++++++++++
    +     MAD-X 5.04.02  (64 bit, Linux)       +
    + Support: mad@cern.ch, http://cern.ch/mad +
    + Release   date: 2018.10.03               +
    + Execution date: 2019.03.13 15:35:42      +
    ++++++++++++++++++++++++++++++++++++++++++++

Once this works, proceed to clone madgui and setup madgui::

    git clone git@github.com:hibtc/madgui
    cd madgui
    pip install -e .

This will also suck in dependencies such as PyQt5 or numpy.

It is important to **always** use pip for installation because pip handles
certain things better than e.g.  ``python setup.py install``. See this `blog
post`_ for one example what can go wrong with the setuptools based method if
you are interested.

.. _blog post: https://coldfix.de/2019/03/14/no-pip-no-sip/

If you have messed up the madgui installation for some reason, the easiest
thing is to destroy your environment and then start a fresh one::

    conda deactivate
    conda env remove -n madgui
