#! /usr/bin/env python2
"""
Run the MadGUI application.
"""
import inspect
import os
import sys

# add local lib pathes
_file = inspect.getfile(inspect.currentframe())
_path = os.path.realpath(os.path.abspath(os.path.dirname(_file)))
for lib in ['event']:
    _subm = os.path.join(_path, 'lib', lib)
    if _subm not in sys.path:
        sys.path.insert(0, _subm)

import madgui.main

if __name__ == '__main__':
    # start the application
    madgui.main.main()
