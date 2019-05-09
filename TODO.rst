priority
========

- MEFI in output file
- extend documentation
- write report on problems with gantry model
- generate import dependency graph


madgui
======

misc
~~~~
- unify orbit corrector widgets

- menu/toolbar item for displaying monitors

- unify orbit corrector with beam diagnostic dialog SAME PROCEDURE
- dispatch events in later mainloop iteration

- unify:

    - src/madgui/online/orm_measure.ui
    - src/madgui/online/offcal.ui
    - src/madgui/widget/correct/autoproc.ui
    - src/madgui/widget/correct/orm_measure.ui

    - opticsEditWidget

        KnobSelectWidget
        OpticsTableWidget
        Form:

        - Filter knob name
        - import from file "open"/"save"
        - import from focus "1,2,3,4" "read"
        - use deltas "0.1, -0.2

    - procedureSetupWidget

        - used shots
        - ignored shots

    - running export
        - export dir
        - dataseries [time, knobs…]
        - dataseries [time, monitor…]

        requires NewValueCallback + MEFI changed notification for useful operation

- use DoubleSpinBox stepType = AdaptiveDecimalStepType (not too useful)

- simplify matcher…, do we really need all that start/stop fuzz?

- let backend provide control for selecting MEFI -> textedit pattern

- option to save all log items

- autodetect steerer usability for X/Y based on sectormap / ORM? -> unnecessary
  at least put out a warning?

- fit transfermap, show chisq/likelihood

- simplify model loading
- simplify model.twiss() , should be able to pass twiss_args

- matching: improve defaults element/constraint/variable when adding
  constraints/variables

- startwerte für temp variablen in assign

- undo: CALLing files by diffing both elements/variables/beam

- proper range support

- simplify destroy/remove mechanisms

- strength mode: click on elements -> change strength

- save pandas dataframes instead of cpymad.Table?

export
~~~~~~
simplify export file formats, IDEAS:

- hdf5

  - pro: less clutter
  - con: "opaque", always need hdf5 library to access files need dedicated loadfile dialog to access data subgroups

- directory structure with several files alongside each other

    - .str          optics
    - .txt/.npy     array data
    - .yml          metadata
    - .tfs          monitor snapshots / model exports
                    (some metadata)

    - pro: simple, maximum compatibility
    - con: cluttered, non-coherent data

- safeguard against parsing errors, log error
- export .tfs
- export all / import all
- export beam/twiss as .madx files
- export sequence
- export/save model
- use tablib, e.g. https://github.com/kennethreitz/tablib ?
- all
- model
- sequence
- reverse sequence

- unify import/export mechanism for globals in menu vs GlobalsEdit

    -> add import from .str in GlobalsEdit

orbit corrector
~~~~~~~~~~~~~~~
- unify all three modes into one widget

- button "procedure" -> popup dialog

    - none
    - multi grid
    - multi optics
    - measure ORM directly
    - manual

- button "readouts" -> popup dialog

- choose mode via:

  - Orbit response: "[Show]"

    - numerical orbit response
    - MATCH
    - sectormap

  - "Backtrack" / "Estimate model orbit":

    - no shot (use current model)
    - single shot (multi grid)
    - multi shot (multiple optics):

          - manual
          - auto

undo stack
~~~~~~~~~~
- state based or transition based (revisions vs UndoCommand)
  -> full model snapshot each time

- unify all Model._update_XXX methods to allow merging multiple undo
  commands

- remove intimate knowledge about Model invalidation from undo stack!
  (see undostack.rollback -> model._twiss/invalidate)

- elevate undostack onto a strictly higher level than model itself

    - "pure" model, i.e.: (globals, elements, beam, twiss_args)
    - manage model separately from MAD-X
    - madx.apply_model(model)

    - transitional:

        - pass Boxed(state) to Model
        - Model subscribes to state.changed

    - pro: decouple model from undostack

- can we automatically pick up on changes in MAD-X?

uses

- mainwindow: undo/redo/qundoview
- procedure/match: rollback/macro


plot
~~~~
- introduce a new `madgui.collections.Dict` type (similar to List)?

  - makes add_curve/del_curve trivial
  - check whether this could be be useful in other places


- design criteria for scene graph:

  - uniform mechanism to enable/disable nodes (at least nice-to-have)
  - invalidate individual parts of the graph without redrawing everything
    (should check at some point whether this *actually* makes sense)
  - named nodes (externally or internally)
  - consistent mapping between data and node

- add plots for "Survey position" "Survey angle" "Sectormap.rXX"
  -> introduce prefixes "survey." "twiss." "sector." for the table to be used

- easier plot customization
- multiple curves in same figure

- add curvemanager to session?

errors
~~~~~~
- manage list of errors in model
- add "errors" section to model file
- add "load errors" to gui
- add "load errors" for TestACS stub
- install errors using expressions:

    XXX__eff = XXX * (1 + XXX__drel) + XXX__dabs

    knobs: XXX = knob name
    attrs: XXX = "elem.attr" ??

- improve ealign handling (``eoption, add=false``!)
- compacter notation efcomp notation

events
~~~~~~
- global event registry / manager? (similar to pydispatcher)

- weakref to func.__self__

- rename boxed -> maybe/Var/Observable/Subject/BehaviourSubject?
    add .map/.as_attr/.unbox method
    add .bind method?

- note: RxPy's BehaviourSubject is close to what we want…


config
~~~~~~
solution for cleaner config lookup?:

- lookup config via window -> parent (?!)
- connect to config.number.changed when shown, disconnect on hide
- rework config… simply nested attrdict?


ORM analysis
============
- monitor errors

- fast mode with sectormap
  -> quadratic map for more accurate predictions?

- minimize several independent recordings simultaneously

- simplify model.errors module, integrate into Model?

- integrate ORM plot in madgui itself

  - allow to plot sectormap components, and sigma components
  - make use of twissfigure:

      - element markers
      - status bar info
      - click on element -> select for plot
      - click on element -> show info box?
      - click on element -> show error box

- parallelize
  - ORM computation
  - jacobian

- add code to check effectiveness of different errors for generating ORM
  deviations

- different orbit correction matching algorithms ORM + SVD (etc…):
  http://uspas.fnal.gov/materials/05UCB/2_OrbitCorrection.pdf


orbit correction
~~~~~~~~~~~~~~~~

initialization step:
- lstsq(tm) backtrack

unify API: take 3 tables (as with MAD-X):

- model       modelled orbits x,y,betx,bety,mux,muy at monitors/steerers
- measured    measured orbits x,y at monitors
- target      desired orbits x,y at monitors

  -> is the first parameter enough to fit all the methods? I guess not
     the dynamic ones…

fit methods:

- match (expensive)
- kicks = lstsq(orm, dy)

    - orm=numerical     (expensive)
    - orm=analytical    (uncoupled)     sqrt(β₀β₁)·sin(2π|μ₁-μ₀|)
    - orm=sectormap     (inaccurate)

- multigrid dialog:

    - improve behaviour of undo mechanism: never add duplicate entries?
    - weights for constraints?

diagnostic dialogs
~~~~~~~~~~~~~~~~~~
- fix dispersion
- fix 4D

model
~~~~~
- rename madgui.model to madgui.phys?
- move emittance maths here
- rename orm module to orbit_response

- saving model
- automatically use last twiss on load (do not recompute)
    -> can mostly discard model files?
- menu item "use MAD-X twiss parameters (i.e. normal coordinates)"

- implement twiss column transformations (envx,gamx,…)
  in terms of TwissData wrapper, both hence and forth, i.e.
  do_get_twiss_column/get_elem_twiss and MatchTransform
- obtain individual rows from twiss table

- make use of new cpymad element/beam types:
    - use base_type to determine default values
    - use inform to determine whether attribute was user-defined

update only if there is an actual diff:
    - tableview -> model
    - model -> tableview

- model crash -> restart MAD-X and replay session using undostack (??)
- no, its probably better to have a collective attribute/knob/beam value based model


dialog cleanup
~~~~~~~~~~~~~~
- turn showTwiss->destroyed into a regular method
- simplify singlewindow! (ivar + Dialog?)
- move MainWindow.createControls logwindow stuff to LogWindow

treeview
~~~~~~~~
- no special binding for getter/setters (partial idx value)
- rename `data` -> `value`
- remove i, c from getter/setter signature (make index part of the data
  model in those places where it is needed?)
- remove `TableItem.get_row`
- set datatype explicitly for most items
- provide special FloatItem/StringItem/etc that set delegate accordingly
- simplify `TreeNode.invalidate`
- more fine-grained TableModel._refresh (revert f6ecac30 "Always reset
  model to force index invalidation")
- no separate row-nodes?
- in TableModel.setData: invalidate properly
- implement ``del_value``

- resizing…

    - don't trigger column recalculation when the TreeView size changes due
      to column resizing
    - keep user resized columns

floor plan
~~~~~~~~~~
- true 3D with opengl
- improve camera movement
- customize settings via UI (wireframe etc)
- export to 3D model

knobs
~~~~~
- fix handling for ``kick``
- extend knowledge about knobs:
    - dependent variables/elements
    - recursive expressions

beam diagnostic
~~~~~~~~~~~~~~~
- sanitize + unify different procbot widgets, esp. offcal…
- simplify multi_grid/optic_variation / mor_dialog (!!!)…
- use procbot in online.offcal
- join these into the same dialog?

- multi grid method:

    - allow hiding readoutsView
    - disabling backtracking

- optic variation -> two dialogs

    - monitor dialog -> need "record" function and remove/enable individual
      records on demand. records should store sectormaps and knob values
    - matching dialog (as with multi grid dialog)

- emittance dialog:

    - clear distinction x / y / xy
    - multiple optics

unit-handling
~~~~~~~~~~~~~
- improve unit handling with TableView…, should be easy/builtin to switch
  between different display modes for units:

    - inline (QuantityDelegate)
    - unit column
    - in gray in name/parameter column
    - hidden
    - column title (?)

- get rid of QuantityValue / QuantityDelegate / QuantitySpinBox ???
    -> probably not for now, but should be simplified

param dialog
~~~~~~~~~~~~
- add ``auto_expand`` flag to TreeView, default=True
- make "Summary" tab expandable, but auto_expand=False
    SBEND: kick -> k0

- show the "(expression)" as first child
- don't autoexpand below expression
- warn when overriding an attribute/expression by a value

toolbar/...?:
- update (refetch) [makes config.number.changed subscription less important]
- use scientific / normal notation
- auto-expand
- show as list / table [for matrix tables]
- show expressions

- merge ParamInfo structs
- enum dropdown for selecting ui_unit
- save unit/ui_unit for all parameters into session file

- spin box: input values while updating view (disable update?)
- keyboard editor control

element info box: DVM tab
    - associated dvm parameters
    - letzter gitter messwert

plotting
~~~~~~~~
- simplify creating plots for user
- simplify/document defining custom plots in config, i.e. curve names etc
- plot API in python shell
- replace matplotlib by pyqtgraph?
- configure "show element indicators" via model/config + toolbutton
- fix "shared plot" when showing monitors: different shapes/colors for X/Y

- encapsulate the envx/envy/etc transformations in model fetch/match
- plotting differences between revisions, closes #17

- add "frozen" mode to plot widgets (unsubscribe from Model.updated)

- plot legend outside plot

- curves: export

MatchDialog
~~~~~~~~~~~
Priority: medium

Add/implement the following features:

- (+) global constraints
- (0) summary table (chisq...?)
- (-) filter duplicate constraints
- (-) constraint ranges
- (-) method: lmdif / ?

async
~~~~~
Priority: low

We could make use of the new ``async/await`` syntax in python 3.7 to write
sequential code for asynchronous operations. For an example how to do it, see
udiskie_.

.. _udiskie: https://github.com/coldfix/udiskie/blob/master/udiskie/async_.py

- coromin
- threading/async for loading elements / long running tasks
- use beamoptikdll in background thread?
    -> i believe it must be called in the main thread


cpymad
======

- use MAD-X' builtin chdir once MAD-X 5.05.00 is available

- live query element parameters
- slice of Elements

cpymad NG (3.0?) ideas
- implement all logic in cython
- refactor class Madx to module
- make Madx a pure rpyc wrapper
- use rpyc for simple proxying?
- integrate model again

packaging:

- new repo libmadx that builds madx as static/shared library:
    - conda-package for windows
    - manylinux for linux
      (I'd rather NOT use conda for linux since I don't expect the build
      would be as compatible as manylinux)
    - upload to pypi
    - use the libmadx package for building cpymad

- add build scripts for linking MAD-X dynamically:
    - deploy libmadx.dll
    - create libmadx.lib import library
    - set zip_safe=False in setup.py


hit_models
==========

- handle validity of SD values individually (-> H/V-monitor)
- fix sbend lengths (have sub mm deviations)


hit_acs
=======

- halbwertsbreiten -> RMS breiten
- hit_acs.stub:  UI to sync beam/twiss_args


pyqtconsole
===========

- ctrl+Z can revert into inconsistent state
    -> set readonly, handle all events
        - text insertion
        - home/end
        - left/right/up/down
        - backspace/delete
        - ctrl+Z, ctrl+Y, ctrl+A, ctrl+shift+C, ctrl+V
