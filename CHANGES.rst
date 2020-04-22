CHANGELOG
~~~~~~~~~

20.4.1
~~~~~~
Date: 22.04.2020

- Add constrain to the match feature. If the residual is too high, then the
  optics are not changed

20.4.0
~~~~~~
Date: 08.04.2020

- Add execute button to match widget
- Downgrade pyqtconsole to 1.1.3
- Add sample_model dependency

20.1.0
~~~~~~
Date: 25.01.2020

- revisit auto load model feature
- auto loading was subtituted by a button in the read strengths dialog
- updating pyqtconsole dependency to 1.1.5

19.8.0
~~~~~~
Date: 19.08.2019

- add auto load model feature

19.6.3
~~~~~~
Date: 06.06.2019

- use the ORM orbit correction method by default
- add tooltips for the elementinfo tabs


19.6.2
~~~~~~
Date: 05.06.2019

- fix exception in GLWidget.closeEvent
- explicitly request OpenGL version to improve chances of getting a 3.0 context
- request OpenGL 3.2 core profile (disallow deprecated features) to avoid
  running into backward incompatibilities later on


19.6.1
~~~~~~
Date: 05.06.2019

- fix menuitem "Interpolation points" not updating the plot
- fix monitor indicators not being updated after de-/selecting monitors
- fix 3D survey widget by adding missing shaders to the installation
- log OpenGL version and show a nicer error message for incompatible version
- fix incorrect display of element indicators after sequence reversal
- cpymad 1.2.1 fixes deadlock that occurs when clicking "About MAD-X" menuitem
  in application context without stdin (e.g. windows GUI)

19.6.0
~~~~~~
Date: 02.06.2019

- fix exception when using element info after opening new model
- deal with issues of lingering signal handlers of the element Selection
  after opening new model (by voiding the selection)
- decrease alpha for element indicators

19.5.5
~~~~~~
Date: 27.05.2019

- fix drawing elements only once that occur multiple times in sequence
- add more documentation
- split twiss widget code from plotting module to allow using the plot
  functions externally without importing GUI code

3D survey widget:
    - fix bug in diffuse lighting direction calculations
    - show thin elements as discs
    - show more element types, colorful crowd
    - fix not drawing the initial model
    - scale number of points on circles with radius

19.5.4
~~~~~~
Date: 16.05.2019

- add true 3D OpenGL based survey widget (WIP)
- fix exception in curvemanager tool when clicking snapshot button
- fix TypeError when importing a table without a text column
- show warning when entering invalid number format (instead of silently
  ignoring the invalid input)
- show warnings when ignoring invalid knob strings


19.5.3
~~~~~~
Date: 13.05.2019

- allow negative values in step field (ORM measurement dialog)
- fix AttributeError if using model without undo stack
- fix ValueError for "Add" button in match dialog
- separate "Write strengths" menu item further from "Read strengths"
- add hotkey for "Read strengths"
- find models in breadth-first manner, not depth first
- fix bug that caused incorrect update when changing plot, especially from
  plots with many curves to plots with less curves


19.5.2
~~~~~~
Date: 11.05.2019

- add a selection of survey/sectormap plots
- show legend outside graph by default in shared plot mode


19.5.1
~~~~~~
Date: 11.05.2019

- show UndoStack.macro invocations in the logging area
- add menuitem to reverse current sequence inplace (experimental)
- show DRIFT attributes as inherited
- start usrguide (very basic atm), document QT_SCALE_FACTOR
- add toolbar item to show/hide BPMs
- add Backend.read_params method to read all/multiple params
  (requires hit_acs>=19.5.0)
- export full parameter dump in orm measurement procedure
- update to cpymad 1.2.0, MAD-X version 5.05.00


19.5.0
~~~~~~
Date: 07.05.2019

- fix a TypeError when changing the model
- export time along with BPM values in ORM measurement dialog


19.4.4
~~~~~~
Date: 25.04.2019

- fix several minor exceptions that can occur in corrector dialog under rare
  circumstances


19.4.3
~~~~~~
Date: 25.04.2019

- fix RecursionError in ``UndoStack.macro()``, that occurs e.g. when using
  the MATCH/sectormap methods of corrector dialog
- fix potential NameError in ``UndoStack.rollback()``
- fix unwanted signal connections that can lead to TypeErrors and multiple
  signal handler executions (e.g. triggering the EditConfigDialog twice)


19.4.2
~~~~~~
Date: 24.04.2019

- fix log widget to have monospace on windows
- fix exception when setting max log size via menu
- fix exception in corrector dialog when using MATCH or sectormap methods:
  "TypeError: macro() missing 1 requried positional argument"
- fix TypeError in corrector dialog when changing config (combo box):
  "TypeError: itemText(self, int): argument 1 has unexpected type 'str'"


19.4.1
~~~~~~
Date: 13.04.2019

- fix empty log after changing log level
- improve performance of log widget even after long use (#35)
- add menu and config entry for setting a maximum log length
- fix log entries without specified color receiving the color from the
  previous entry
- improve non-GUI mode app support
- make it possible to show the mainwindow on top of other windows, by turning
  dialogs into top-level windows
- simplify Dialog instanciation and internal logic
- fix the "Calibrate" button in "orbit correction -> measured response"
  widget. It was missing the implementation after an earlier refactoring
- implement notifyEvent in terms of eventFilter. This makes it possible to
  these event notifications, and therefore prevent bugs due to calling dead
  objects.
- turn shell from dockwidget into a normal dialog
- allow opening multiple console windows at a time
- replace qtconsole by the faster and more lightweight pyqtconsole
- this fixes an "AttributeError" when calling "exit()"
- also fixes "Execution aborted" error that prevents further statements from
  being executed in the console after any exception has been raised in a
  previous command
- work on improving documentation and cross-referencing
- use pint 0.9


19.4.0
~~~~~~
Date: 01.04.2019

- drop python 3.5 compatibility, require at least 3.6
- fix exception when trying to show plots if loading a madx file that includes
  a ``SELECT, flag=TWISS`` command
- fix weird matplotlib offset behaviour when showing a nearly constant quantity
  (by plotting an invisible horizontal line at y=0)
- add menuitem to redo twiss and refresh plot
- add menuitem to set number of interpolation points
- add config entry for number of interpolation points
- fix some warnings/errors in documentation
- replace QUndoStack by our own implementation to simplify using Model in
  non-GUI contexts
- remove QUndoView for now (limitation due to replacing QUndoStack)
- simplify setup.py using static metadata and rework travis scripts


19.3.3
~~~~~~
Date: 21.03.2019

- install as gui script
- fix ``ValueError: fallback required but not specified`` in pyqtconsole due
  to missing stdout when called as gui script


19.3.2
~~~~~~
Date: 21.03.2019

- fix TypeError: set_draggable() missing 1 required positional argument
  (in shared plot mode)
- add units in curve y labels
- change some quantity labels
- separate function to edit model parameters, for use in plugins etc


19.3.1
~~~~~~
Date: 12.03.2019

- add missing file ``twissfigure.yml``
- add ``import_path`` config entry for adding plugin folders to ``sys.path``
- expand '~' and environment variable in config: ``run_path``, ``model_path``,
  ``import_path``, ``session_file``


19.3.0
~~~~~~
Date: 12.03.2019

- drop python 3.4 support
- remove the "by delta" checkbox in orbit correction dialogs, always use the
  measured monitor position if possible
- depend on cpymad 1.1.0
- auto-update plotted monitor markers
- fix Ctrl+P closing mainwindow
- handle menu hotkeys within all application windows
- add menu options and hotkeys to increase or decrease font size
- remember font size setting
- some bugfixes
- remove obsolute "Update" buttons from diagnostic dialogs

internal:

- move ORM analysis code its own independent package
- add PyQt5 as regular dependency (can automatically installed via pip)
- add tests on py35
- refactor modules in ``madgui.plot``
- remove context-managing ability from ``Session``
- replace ``pyqtSignal`` by our own lightweight solution (in preparation for
  letting models etc be instanciated without GUI)
- not subclassing ``cpymad.madx.Madx`` anymore, moved functionality directly
  to cpymad
- refactor/simplify caching classes
- make ``twissfigure`` module more independent from mainwindow/session and
  simplify plotting API (standalone functions that can be used without madgui)
- refactor scene graphs, prepare for fully consistent management of all scene
  elements via curvemanager dialog
- optimize performance when updating plot
- fix error while building the documentation
- start a developer's guide documentation section
- introduce a lightweight history type to manage history in several components
- use PyQt5 imports directly, remove the ``madgui.qt`` compatibilty module
- split up the correction dialogs into components, in preparation for a great
  unification


19.01.0
~~~~~~~
Date: 19.01.2019

- fix SyntaxError in py3.4
- internal development of ORM analysis utilities
- add method to model to reverse sequence inplace
- generalize and slightly simplify the orbit fitting API
- treat only "direct" variables (i.e. not deferred expressions) as knobs
- search for knobs recursively through deferred expressions
- parse unit strings from ACS backend on the fly
- adapt to the renaming hit_csys -> hit_acs
- adapt to changes in hit_acs 19.01.0
- basic version of measured response method for empirical orbit correction
- install a common BeamSampler that monitors and publishes new readouts


18.12.0
~~~~~~~
Date: 11.12.2018

Updated dependencies:

- update to cpymad ``1.0.10``
- new dependency on scipy!

Bug fixes:

- fix a TypeError in beam tab widget
- fix bug that some widgets are shown only on second click
- explicitly specify the correct datatype for most editable tables
- fix exceptions in some import routines
- fix exception when starting without config file
- fix early exception on some systems due to encoding name

Misc:

- display sectormap and beam matrix as matrix-like table
- improve lookup logic for beam matrix
- remove the "Expression" column in favor of a composite edit widget
- some internal API changes
- add fitting API in ``madgui.util.fit``
- allow loading table files with text column
- infer missing ``S`` from ``name`` column loading table files
- autogenerate apidoc files during travis build
- update travis config for phased out support of container based infrastructure
- mark build as dev version by default (travis)
- recognize that consts cannot be used as knobs
- move load_yaml function to ``madgui.util.yaml``
- add simpler API for back-fitting orbit
- never require betx, bety when backtracking
- development on the ORM utility API


18.10.3
~~~~~~~
Date: 31.10.2018

bugfixes:

- fix undo feature not working because of using the wrong stack
- fix exception in Model.twiss when a table is specified

ORM analysis:

- share get_orm() implementation with orbit correction
- deduplications, several code improvements and simplifications
- use base_orbit to backtrack initial conditions
- add plot functions to the analysis script
- better output
- add ability to fit X and Y independently
- compacter ealign notation in undocumented spec file


18.10.2
~~~~~~~
Date: 25.10.2018

bugfixes:

- fix for missing setObsolete on Qt<5.9 (was previously fixed only partially)
- fix empty list of optic elements in output file
- fix beamoptikdll not initiating device download due to flooding
- fix duplicate value bug in the readout logic
- decrease chance of race condition leading to inconsistent readouts

UX improvements:

- log to main logwindow as well
- increase logging verbosity during orbit response measurements
- flush file after each write
- vary steerers in sequence order
- avoid one redundant readout
- increase default steerer variation to 0.2 mrad

ORM analysis:

- handle missing ORM entries as zero
- restrict to used knobs
- fix empty steerers field in record file
- handle accumulated errors in ORM analysis
- add simple plotting script


18.10.1
~~~~~~~
Date: 20.10.2018

- fix exception when opening matching dialog
- fix bad fit_range leading to bad initial conditions fit
- add safeguard for ``None`` offsets in corrector widgets
- restrict orbit correction to only X/Y constraints
- let user choose whether to fit the difference between measured and design
  values or just fit the design value directly (this can be different in case
  the backtrack does not describe the monitor values very good)


18.10.0
~~~~~~~
Date: 18.10.2018

Now in calver_ (calendaric versioning) ``YY.MM.patch`` since this better fits
the nature of madgui development and is I believe more useful for end-users.

.. _calver: https://calver.org/

New features:

- add app icon as .ico file (for shortcuts etc)
- add orbit response matrix (ORM) based mode for orbit correction
- add even simpler mode that assumes orbit response matrix = sectormap
- add method selection to OVM dialog
- add dialog for recording orbit response matrix
- add script for generating test ORM recordings
- add script for analyzing ORM recordings

Improvements:

- can edit the steerer values before executing
- implement prev/next buttons in optic variation dialog
- allow multiple floor plan windows
- prevent annoying busy cursor due to MPL redraws
- turn on warnings for our own modules
- close and wait for the MAD-X process properly
- improve update of steerer/monitor display tables
- don't automatically create logfile for every MAD-X session anymore
- make MAD-X less verbose: command echo off!

Bug fixes:

- fix ``AttributeError`` when clicking ``Apply`` in optic variation dialog
- fix ``NameError`` when opening curve manager widget
- fix missing reaction to changing selected config in OVM dialog
- fix missing update before recording in OVM automatic mode
- fix ``AttributeError`` after editing config in MGM dialog
- update the config combo box after editting config
- fix current config not being updated after editting config
- fix jitter option…
- fix several DeprecationWarnings
- stop ORM procedure upon closing the widget
- fix status messages for export menuitems
- fix bug in Model loader (path)
- fix ``yaml.RepresenterError`` when no csys backend is loaded
- fix error when loading stand-alone .madx file
- misc fixes to corrector code
- use button groups to safeguard against deselecting radio buttons

Meta:

- add sanity checks (pyflakes, hinting to missing imports, syntax errors, etc)
- add automatic style checks (pycodestyle)
- add first tests for the (now) non-UI components: model/session/corrector
- add rudimentary documentation (updated when pushing to master)
- automatically upload release to PyPI when pushing tags
- move source code to unimportable subdirectory

Refactoring:

- improve naming: set_rowgetter -> set_viewmodel
- deduplicate code between optic variation and multi grid modules (OVM/MGM)
- remove our ElementInfo proxy class, simply use Element from cpymad
- remove several obsolete/unused methods, dead code
- shared management of monitor readouts
- move AsyncReader functionality to cpymad
- make use cpymad multiline input for collected commands
- auto show SingleWindow widgets
- simplify access to twiss table
- let the online plugin manage its settings menu
- relocate several modules and classes
- demeterize Model: no GUI, no config, no graphs!!!!
- remove several static configuration items for MAD-X data structures that can
  now be introspected via cpymad
- globalize several private methods that don't need to be part of class
  interfaces
- slightly simplify the twiss args guesser
- lose obsolete thread utils [core.worker, QueuedDispatcher]
- don't need thread-safety anymore (no more threads…;)
- rename control._plugin -> .backend
- remove the need for a separate Loader class
- add ``Model.changed`` overload that passes old and new value
- inline and simplify several methods
- introduce a new ``Session`` object that replaces ``MainWindow`` as context
  object and can be used without active GUI
- DRY up MANIFEST.in
- demeterize ProcBot for non-GUI usage
- make the Corrector GUI-independent
- move recording/export responsibilities to Corrector (from CorrectorWidget)
- let Corrector know only the active configuration

…and many more


1.14.0
~~~~~~
Date: 24.07.2018

- refactor and simplify treeview data model, more cohesive table definitions
- monospace in tables
- autosave and restore online settings (MEFI)
- fix missing QUndoCommand.setObsolete on Qt<5.9
- allow defining a ``limits`` parameter in multigrid config
- fix IndexError if too few monitors are selected
- implement missing export functionality in orbit/emit dialogs
- use ``data_key`` for initial conditions im-/exports
- add import/export menus as in mirko
- implement strength import from YAML
- refactor import/export logic
- set YAML as the default filter in strengths export
- recognize '!' comment character in .str files
- fix treeview edit spin boxes to fit into their column
- highlight changed items in SyncParamWidgets (read/write strengths)
- highlight explicitly specified beam/twiss parameters in bold (initial
  conditions dialogs)
- code deduplication among diagnostic dialogs: share same rowgetter method
- save selected monitors for orbit/optics in different lists
- support QTableView again in parallel to QTreeView, this has some advantages
  such as supporting background colors
- highlight changed steerers in bold in multigrid dialog)
- rework the optic variation dialog, based on tableview, added automation UI
- disable section highlighting in TableView
- refactor how variables are stored in orbit correction dialogs
- always show the current value versus the "to-be-applied" value in the
  "steerer corrections" table
- add back/forward button in orbit correction dialogs
- nicer arrow buttons (QToolButton) in element info dialog
- show monitors during orbit correction


1.13.0
~~~~~~
Date: 15.07.2018

- simplify the activate logic of the curvemanager tool (was a toggle item with
  complex behaviour, is now simply a button that will create the widget)
- add "Ok" button for curvemanager widget
- fix beam diagnostic dialog staying open with blank tab when pressing Ok
- remove explicit dependency on minrpc version from setup.py (possibly fixes
  problem where cpymad's requirement on the minrpc version is then ignored)
- improve knob selection/input in match dialog
- change how "assign" expressions must be defined in the multigrid config, can
  now be bound to only x or y specifically
- add widget for optics-based offset calibration
- use backtracking as method for calculating initial coordinates (instead of
  inverting sectormaps)
- some code deduplication between diagnostic dialog and multigrid
- allow to specify matching 'method' (lmdif/jacobian/…) in multigrid config
- can show/hide timestamps in the log window
- make treeview columns user resizable (will be reset whenever the view
  changes size)
- simplify stretch logic and remove custom column stretch factors
- minor cleanup for some ColumnInfo definitions


1.12.0
~~~~~~
Date: 26.06.2018

- add "About python" menuitem
- fix bugs in ``Model.get_transfer_maps`` / ``Model.sectormap``
- collect multiple variable update commands into one RPC call
- add class for boxing generic values
- make ``Mainwindow.model`` a ``Boxed`` object!!
- remove ``Model.destroyed`` signal in favor of the more general
  ``Boxed.changed`` signal
- add ``envx``/``envy`` columns to ``get_elem_twiss``
- fix data export in "Read strengths"/"Write strengths" dialogs
- set "Ok" as default button in export widgets
- add menuitem for executing MAD-X files (i.e. CALL)
- remember folders separately for "load strengths" and "execute file" items


1.11.4
~~~~~~
Date: 11.06.2018

- fix inconsistency with open-/closedness of sectormap intervals in
  ``model.sectormap`` and ``get_transfer_maps``


1.11.3
~~~~~~
Date: 11.06.2018

- add 'export strengths' menu item
- add export as .str file in globals edit
- fix JSON incorrectly being listed as export format
- show globals according to var_type (predefinedness)


1.11.2
~~~~~~
Date: 11.06.2018

- fix losing zoom/view on every curve redraw due to autoscaling
- fix AttributeError when trying to save session data. This appeared only if
  online control was not connected and prevented saving the current model,
  folder etc
- fix ValueError when computing relative path for a model on different volume
- let madgui have its own taskbar group on windows
- add preliminary window icon
- more consistent behaviour for model.get_transfer_maps
- prettify default output format for numpy arrays in python shell

element indicators:
- more distinctive lines for monitors
- flip displacement for pos/neg dipole strengths
- scale displacements/quadrupole colors according to magnet strength
- draw element indicators in background
- distinguish twiss curve by adding outlines
- set alpha=1 for element indicators
- add KICK marker within SBEND
- highlight selected and hovered elements


1.11.1
~~~~~~
Date: 01.06.2018

- fix deadlock appearing mainly on windows during MAD-X commands with long
  output (the fix will cause minor performance degradation for now)
- avoid some unnecessary updates/redraws on startup
- remember *which* online plugin to connect to
- some more info log statements
- change ``onload`` again to be executed before loading the model


1.11.0
~~~~~~
Date: 31.05.2018

Miscellaneous:

- require cpymad 1.0.0rc3
- fix multi grid view not being updated
- add units for K0
- update floor plan survey after twiss

Matching:

- group multiple matching constraints at the same element and position
  into one statement
- specify weights only for the used quantities
- disable matching if the number of constraints is incorrect
- don't reset matching when deactivating the match mode

Element/param dialogs:

- fix condition for when globals are editable
- display element attribute names in title case again
- show leading part of variable names in lowercase
- make use of cpymad's ``inform`` and ``var_type``

TreeView:

- improve/refactor internal tableview API
- use tree view
- expand vectors in tree view
- expand variables occuring in expressions in GlobalsEdit/CommandEdit

Undo:

- support undoing simple .str files
- remove flawed accept/reject logic, i.e. "Cancel" buttons, leaving only
  "Ok" buttons for now (the logic required to properly implement "Cancel"
  is nontrivial, and the behaviour might still be confusing)
- move undo utils to their own module
- subclass QUndoStack
- never show empty macros (QUndoCommand.setObsolete)

Plotting:

- share loaded curves between all windows
- handle add_curve/del_curve in mainwindow
- "snapshot" now saves all available twiss data so that when changing
  graphs, the snapshot for the other curves will be shown
- gracefully deal with missing data in user curves (showed exception very
  loudly previously, showing debug message now)
- invert quadrupole focussing color codes in Y plot
- distinguish SBEND/KICKER sign by shifting the indicator position up/down
- smaller but more distinct indicators
- fade out "off-axis" kickers (e.g. HKICKER in Y plot)
- remove grid lines in Y direction
- fix missing element name in status bar
- update element markers on each draw


1.10.1
------
Date: 15.05.2018

- fix ``ElementList.__contains__``
- show/edit expression field for global variables
- fix SyntaxError on py34
- require cpymad 1.0.0rc2
- use ``e_kin`` only if it was given explicitly when editting beam
- more accurate undo handling for setting *new* parameters
- use space-insensitive string comparison before updating expressions
- fix bug that results in squared UI unit conversion factor during matching
- use the builtin unit conversion mechanism in match widget
- allow overwriting deferred expressions by direct values when editting
- fix for not tracking modifications to element attributes on the undo stack
- fix obsolete checks that would prevent certain updates to element attributes
- simplify and unify ParamTable flavours by relying on model invalidation
- implement "expression deletion" by replacing them with their values
- make "Expression" field immutable for string attributes


1.10.0
------
Date: 13.05.2018

- execute ``onload`` commands *after* loading models
- add coordinate axes and size indicator to floor plan
- use ``logging`` for warnings in emittance module
- use the global logger instead of personal loggers
- fix bug in TableView that can cause using the wrong quantity for unit conversion
- knobs are now exclusively global variables occuring in deferred expressions
- remove ``Knob`` class
- don't show units in globals dialog nor in matching dialog
- show globals names in uppercase
- use .ui file for mainwindow
- add UI for filtering shown log records in main window
- suppress MAD-X output by default
- refactor and cleanup TableView API considerably; the old ``ValueProxy``
  classes are now replaced by ``Delegate`` classes that no nothing about the
  individual cell and a ``Cell`` class that provides a context
- allow specializing virtually all data roles by passing an apropriate value or
  callback function to ``ColumnInfo``
- unify and improve handling of checked columns
- remove config item for left/right number alignment
- introduce offsets for monitor calibration
- add naive way to define monitor offsets as the difference between model and
  measurement
- keep monitor values in MAD-X units internally
- add units to column title for several table views
- add "Expression" column for elements
- highlight user-specified values using bold
- remove ``DataStore``, replaced by simplified TableView API and getter methods
- fix energy/mass UI units
- add "E_kin" field for beam
- fix exception in YAML params exporter
- fix bug in sectormap due to interpolate
- compute sectormap only once between changes, and only on demand
- fix missing redraw after ``twiss``
- fix editing ``kick`` (works only for HIT-model style angle/k0 definitions)
- remove ``Element.id`` in favor of ``.index``
- remove our own proxy layer for ``Element``, use the cpymad elements directly
- remove support for scalar names referring to vector components ("KNL[0]" etc)
- simplifications for ``ElementList`` and how elements can be accessed
- fix ``open_graph`` always showing "orbit" plot
- make the different beam diagnostic tasks part of a tabbed dialog,
  increase code sharing
- rework the beam diagnostic widgets, layout, buttons, defaults
- remember plot window positions, sizes and graph names
- inline some initializer methods in ``model``
- use undo/redo mechanism and a corresponding history widget that fixes the
  backup/restore mechanism used in several places


1.9.0
-----
Date: 16.04.2018

Improvements:

- add x/y/px/py values to *Twiss* tab in element info dialog
- replot backtracked twiss on every new monitor readout
- consider ``SBEND->K0`` when detecting knobs
- remove conversion mechanism for knobs, this is now the responsibility of the
  model itself (by using appropriate expressions) or the online plugin
- use only user defined variables in deferred expressions as knobs, consider
  fixed numbers as static
- show marks with monitor width/position when opening monitor dialog, can
  select which ones to show
- add update/backtrack functionality to monitor widget
- show unit on the column title
- add simple data export for monitors
- make the monitorwidget child to the main window (so it will be closed like
  everything else when the main window is closed)
- persist some settings across multiple madgui runs using *session* files:
  main window size/position, model, folder, selected monitors
- enable grid in twiss plot (mainly for y=0)
- add ``onload`` config entry for application, and in model
- remove setuptools based entrypoint for online models, must be manually
  loaded by the user using the ``onload`` handler instead
- draw element markers at the exit end of the element
- unify log window with MAD-X input commands, output, as well as logging
  records, based on PlainTextEdit with extra selections in different colors,
  much easier on the eyes and hands! Shows line numbers and times on the left.
- show exceptions in log window as well
- silence Pint redefinition warning
- log interleaved MAD-X input/output in chronological order!
- display line numbers for config edit dialog (multi grid)
- show only the actual MAD-X command parameters in the second info tab
- add ``kick`` attribute for SBEND in summary tab

Bug fixes:

- fix exception on py34: missing ``math.isclose``
- fix exception in floor plan
- fix error in matching due to discarding ``Expression``
- fix unit conversion for gantry angle
- fix multi grid with ``assign`` in config file
- use float edit boxes for target values
- fix input unit of multi-grid target values
- fix bug with disappearing monitor widget (GC related)

Internal changes:

- use function call syntax to get the values from Bool proxies
- remove some remaining py2 compatibility code
- support attribute access and *on_change* signals for config entries, make
  ``config.NumberFormat`` a simple config entry
- rename ``user_ns`` to ``context``
- cleanup some unused imports, undefined names etc (pyflakes)
- replace ``monospace`` function by a simpler one without ``size`` parameter
- remove uppercase restritcion when accessing element attributes
- adapt to changes in cpymad 1.0 API
- flip definition of ``gantry_angle`` (``SROTATION->ANGLE`` has changed in
  MAD-X 5.04.00)


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
