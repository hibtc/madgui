Installation
############

In order to install madgui, it is just necessary to have installed both cpymad_ and MAD-X_. Depending on the platform you are working with, the requirements to run madgui are more or less different. Note that the installation has only been tried on Windows and Linux.

.. _MAD-X: http://mad.web.cern.ch/mad/

Installation of madgui (Windows)
================================

To install madgui on Windows, first there might be a couple of required packages that have to be installed.
The most comfortable way to this, is by setting a Conda environment, which is offered by the Miniconda_ or the Anaconda_ distribution.

.. _Miniconda: https://docs.conda.io/en/latest/miniconda.html
.. _Anaconda: https://www.anaconda.com/distribution/#download-section

After the installation, follow the instructions given in cpymad_. There you can find the intructions to set a proper environment and run madgui.

.. _cpymad: http://hibtc.github.io/cpymad/installation/windows.html

Installation of madgui (Linux)
==============================

If you still don't have a Conda distribution, get one. (Take a look at Miniconda_ or Anaconda_).
Set up first a virtual environment for the installation of madgui::

  conda create -n madgui python=3.7

And activate the virtual environment with::

  source activate madgui

It is quite practical to first set pip in your virtual environment::

  conda install pip

Now create a directory for cpymad and download the source from github::

  mkdir cpymad
  cd cpymad

You can now run the command::

  pip install cpymad

or download and build manually with::

  git clone git@github.com:hibtc/cpymad.git

and finally::

  python setup.py install

In this variant of the installation an unofficial precompiled version of MAD-X is used to avoid rebuilding. (See libmadx-dev_)

.. _libmadx-dev: https://github.com/hibtc/madx-debian

To check if everything is fine run the following code line in the terminal::

  python -c "import cpymad.libmadx as l; l.start()"

And you should get as output something like this::

  ++++++++++++++++++++++++++++++++++++++++++++
  +     MAD-X 5.04.02  (64 bit, Linux)       +
  + Support: mad@cern.ch, http://cern.ch/mad +
  + Release   date: 2018.10.03               +
  + Execution date: 2019.03.13 15:35:42      +
  ++++++++++++++++++++++++++++++++++++++++++++

Now madgui::

  cd ..
  mkdir madgui
  cd madgui

You can as well download and install manually::

  git clone git@github.com:hibtc/madgui.git
  python setup.py install

or just run::

  pip install madgui

It is probable that some packages might be missing in your enviroment, for example numpy or PyQt5, so just install them in your environment with::

  conda install numpy
  conda install PyQt5

if this fails, for example with PyQt5, try::

  pip install PyQt5

Repeat until all the required packages are in your environment and try again to install madgui. If everything worked well, you should be able to run::

  madgui

On the terminal and the programm should start.
