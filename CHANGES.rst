CHANGELOG
~~~~~~~~~

2.7.0
-----
Date: (in preparation)


- rename back to madgui
- new versioning scheme: interpret old madgui 0.X.Y -> 1.X.Y, madqt 0.0.X -> 2.X.0
- remove pytao binding
- match dialog: dropdown menu for knobs, minor visual improvements
- internal refactoring, module renamings
- can connect online control without loaded model

0.0.6
-----
Date: 26.01.2018

- element info box: add UI to switch element
- floor plan: support 3D models (no more curved sbends anymore though…)
- floor plan: add UI to change view perspective
- floor plan: fix mirror inversion
- main/plot window: set window title
- main window: add config setting for initial position
- codebase: unify the workspace/segment mess, now only have 'model' again
  (it's unlikely that we will ever be able to work on less/more than one
  sequence in the same workspace anyway)


0.0.5
-----
Date: 24.01.2018

- fix mass unit in MAD-X
- massive simplification of knobs API for interfacing control system
- can read beam parameters from online plugin
- show updated orbit plot after fitting in orbit-correction-mode (regression)
- open orbit plot for orbit-correction-mode


0.0.4
-----
Date: 09.01.2018

- Emit signal when workspace is changed (for plugins…)
- Show about boxes only if the package exists
- Add about dialog for pytao
- Change tab in settings dialog when clicking menu
- When user invokes an action via a menu and the corresponding dialog
  already exists, focus the existing window
- No longer show checkboxes for twiss/beam dialogs in menu
- Read spinbox setting from config
- [regression] Fix exception (closed logfile) when opening different model
- [regression] Fix exception in online-control module when changing values
  into MAD-X


0.0.3
-----
Date: 06.01.2018

- fuzzy select when removing constraints in matching mode (middle click)
- start log threads as daemon thread (never blocks program exit)
- thread safe access to madx/tao
- fetch element data for indicators in background
- fix missing .ui files in installation
- fix crash on windows at startup when starting via gui_scripts entrypoint


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
