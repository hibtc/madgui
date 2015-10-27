Changelog
~~~~~~~~~

The application is still not nearly production ready. I decided to start
tagging releases anyway to provide a few hints and orientation on what's
going on.


Madgui 0.8.0
------------
Date: 27.10.2015

- reworked models, they now define a single configuration
- added ability to save models
- reworked dialog to edit session details
- a few changes to the internal Widget API
- fixed awkward listcontrol sizing algorithm (mostly)
- added wizard dialog for orbit correction
- some refactoring
- fixed a few bugs
- added a few new bugs ;)


Madgui 0.7.1
------------
Date: 18.08.2015

- fix bug with stripping units for arrays (e.g. elem->KNL)
- fix bug with handling arrays (multipoles) in online controller


Madgui 0.7.0
------------
Date: 18.08.2015

- rework online control API
- embed online control UI + controller


Madgui 0.6.0
------------
Date: 03.07.2015

- fix a few bugs
- depend on cpymad 0.11.0
- support array units
- load config from CWD
- path entry for models in config file
- close child frames on session reset
- migrate model code from cpymad


Madgui 0.5.0
------------
Date: 28.05.2015

- revert to single range display for now
- improve aboutdialog
- fix a minor bug when opening an element info popup window and then
  closing the view window
- show log and shell in separate tabs, don't show all the crust


Madgui 0.4.0
------------
Date: 22.05.2015

- major changes to the internal API and data model
- use MDI frame
- change MAD-X session management
- enable to reset MAD-X session
- more powerful dialogs
