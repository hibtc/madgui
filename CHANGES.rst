CHANGELOG
~~~~~~~~~

1.8.0
-----
Date: 25.03.2018

- remove ``api_version`` entry from model files
- add menu item to load MAD-X file
- autoscale plots when pressing "Home" button
- add shortcut method ``model.sectormap`` for use in ipython shell

- twiss/beam init dialog:
    - remove menuitems for separate init tabs, move to file menu
    - treat attributes specified in the config as reals, not ints
    - update enabled-state of save/open buttons according to current widget

- element infobox:
    - add tab with sectormap for element infobox
    - update title clicking on another element (previously was updated only
      when changing using the combobox)
    - fix "open" button

- both:
    - use spinbox=true by default
    - use QuantityValue for floats (spin to win!)
    - fix editting bool values
    - fix display bug when showing SpinBox for IntValue
    - fix "save" button

- matching:
    - match against variables inside expressions
    - reuse computed init conditions after applying corrections

- internal resource handling:
    - remove PackageResource
    - replace pkg_resources with importlib_resources where appropriate
    - remove madgui.resource package

- ellipses plots:
    - add ellipse tab for init dialog
    - add x/y labels
    - use tight_layout
    - use ui units
    - draw ellipse over grid
    - fix swapped ellipse axes when alpha is negative
    - fix swapped formulas for the half axes

- units:
    - pass values internally as plain floats, convert only for IO/UI (#2)
    - Replace all Expression instances by their values, get rid of
      SymbolicValue
    - introduce globals for ``madx_units`` and ``ui_units`` used for
      conversion
    - format degrees with "°" symbol
    - improve unit labels for lists
    - remove pint units file, use the default one shipped with pint instead


1.7.2
-----
Date: 05.03.2018

- added missing factor 2 in ellipse axes lengths
- don't need AttrDict from new cpymad in this version


1.7.1
-----
Date: 02.03.2018

- fix knobs in skew quadrupoles
- hotfix regression with posx/posy aliases
- compatible with hit_models 0.7.0, hit_csys 0.6.0


1.7.0
-----
Date: 02.03.2018

- compute alfa/beta from sigma matrix for consistency
- expose ``twiss`` variable holding twiss table in python shell widget
- set better display units for some plots
- keep plot axis limits on most updates
- finally start to use position dependent emittances in some places
- add more plots: momentum/dispersion/phase advance/emittance/gamma
- plot monitors as dashed lines
- plot loaded/snapshot curves without markers
- update infobox window title when changing element
- add tab with global variables to init-settings dialog
- add tabs to info box: primary/expert/twiss/sigma/ellipse
- keep position in info-box when refreshing values or element
- fit small tool buttons to text size
- let user click on zero-length elements
- scale interpolation step length with sequence length, to show smooth curves
- default number_format.align=right
- default mirror_mode=True
- fix python shell, when starting madqt as gui_script under windows
- rework the multi-grid dialog (for orbit correction)
- rename back to madgui
- new versioning scheme, interpret: ``0.0.X`` -> ``1.X.0``, acknowledging the
  the ``0.X.Y`` releases of the old wx-based madgui.
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
