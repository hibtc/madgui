Scaling
=======

On high- or low-resolution displays, applications often need to be rescaled
for best experience. You have two options to increase or decrease madgui's
font and widget sizes:


Font sizes
----------

The font sizes can be changed at runtime by pressing ``Ctrl +`` or ``Ctrl -``.
These actions are also accessible via the ``Settings`` menu. If there is a
``session.yml`` file, the current setting will be persisted until the next
time madgui is opened.

These actions internally change the font sizes for all known top level
windows. However, it is possible that the change is not propagated to all
child windows if these are using custom fonts.

Scale factor
------------

Qt allows setting a global scale factor for all widgets via the environment
variable ``QT_SCALE_FACTOR``. This should work for any Qt application without
the application needing to know about it, and therefore more reliable than the
other approach. However, this must be done manually by the user and will not
be persisted by madgui between sessions.

On linux, you can start madgui as follows::

    QT_SCALE_FACTOR=1.5 madgui

On windows either set a global environment variable (Workplace settings),
which will affect all Qt applications, or create a ``madgui.bat`` file with
the following content::

    set QT_SCALE_FACTOR=1.5
    python -m madgui
