Getting started
###############

The best way to get started is to try right away to load an example model. You
should also try your own MAD-X models. To run the model in madgui you must
have a sequence defined, a beam and the twiss command in the input file.
The model won't work in madgui if it does not work in MAD-X.
To make full use of the madgui features we insist to (re-)build your model with
the same structure as in the following example.

Example 1: Sample beam line
===========================

To get started you can download the sample model used for quality assurance
for madgui::

    git clone https://github.com/hibtc/sample_model

Or download it from the same git repository.
To start madgui in the console run the sample model by typing, e.g.::

    madgui sample_model/sample

If you used the madgui installer, open madgui and press CTRL + O and search for the
file sample.cpymad.yml.

A new dialog window will appear displaying a 2D representation of the lattice
in front of you with the beam envelope along it.
This simple example contains most of the elements that play an important
role in ion beam transport.
You can see

- bending magnets in gray,
- focussing (defocussing) quadrupoles in red (blue),
- monitors as green dashed lines,
- corrector kicker magnets as purple lines.

Note, that the colors might vary depending on the OS you are using. 
We recommend to play around with the interface and see it's capabilities.
For instance you can click on "beam envelope" and see
the different quantities that you can choose. You should also try to click on
the "blue i"-icon and try to click on each element. Notice that you can see
the available information of the element. Lastly, try the icon left to the
"blue i" and click on any point in the lattice. See how the program matches the
quantity to the chosen point.

Other examples
==============

You can also find a bunch of examples on the git repository of MAD-X. (See
madx-examples_)

Clone the directory and play around::

  git clone https://github.com/MethodicalAcceleratorDesign/madx-examples

Note that madgui has only been tested for transfer lines. Running an
accelerator model might not work (yet) optimally.

.. _madx-examples: https://github.com/MethodicalAcceleratorDesign/madx-examples
