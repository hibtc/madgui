CHANGELOG
~~~~~~~~~

0.0.3
-----
date: unknown

- fuzzy select when removing constraints in matching mode (middle click)
- start log threads as daemon thread (never blocks program exit)
- thread safe access to madx/tao
- fetch element data for indicators in background
- fix missing .ui files in installation


0.0.2
-----
Date: 05.12.2017

- continuous matching (within any element position)
- fix bugs in matching code
- updated dependencies: pint 0.8.1, cpymad>=0.18.2, pytao>=0.0.1


0.0.1
-----
Date: 30.11.2017

First reference point to define somewhat stable versions.

List of features:

- cpymad/pytao as simulation backends
- plots: alfa/beta/envelope/orbit; and the ones defined by tao
- integrated python shell (ipython/jupyter) not very useful as of yet:
  limited exhibition of objects, no convenient APIs provided (plotting)
- log tab that shows madx/tao output
- tab that shows madx/tao commands
- display and edit box for beam parameters; initial conditions (i.e. twiss);
  and element attributes (read-only so far)
- 2D floor plan
- matching (interactive + dialog)
- emittance (dialog)
- orbit alignment: 2-grid + N+optic methods
