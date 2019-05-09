Getting started
###############

The best way to get started is to try right away to load an example model. You
should also try your own MAD-X models.


Example 1: HIT Models
=====================

To get started you can download the MAD-X models for the transfer lines at the
Heidelberg Ion-Beam Therapy Center (a.k.a. HIT_)::

    git clone https://github.com/hibtc/hit_models

To start madgui and run one of the models type, e.g.::

    madgui hit_models/hht1

You can see that a 2D representation of the lattice is displayed in front of
you with the beam envelope. We recommend to play around with the interface and
see it's capabilities. For instance you can click on "beam envelope" and see
the different quantities that you can choose.  You should also try to click on
the "blue i"-icon and try to click on each element. Notice that you can see
the available information of the element. Lastly, try the icon left to the
"blue i" and choose a point in the lattice. See how the program matches the
quantity to the chosen point.

.. _HIT: https://www.klinikum.uni-heidelberg.de/Willkommen.113005.0.html


Other examples
==============

You can also find a bunch of examples on the git repository of MAD-X. (See
madx-examples_)

Clone the directory and play around::

  git clone https://github.com/MethodicalAcceleratorDesign/madx-examples

Note that madgui has only been tested for transfer lines. Running an
accelerator model might not work (yet) optimal.

.. _madx-examples: https://github.com/MethodicalAcceleratorDesign/madx-examples
