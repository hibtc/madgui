# encoding: utf-8
"""
Main window component for MadQt.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from PyQt4 import QtCore, QtGui

import madqt.core.menu as menu


__all__ = [
    'MainWindow',
]


class MainWindow(QtGui.QMainWindow):

    #----------------------------------------
    # Basic setup
    #----------------------------------------

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.initUI()

    def initUI(self):
        self.createMenu()
        self.createControls()
        self.createStatusBar()

    def createMenu(self):
        Menu, Item, Separator = menu.Menu, menu.Item, menu.Separator
        menubar = self.menuBar()
        menu.extend(self, menubar, [
            Menu('&File', [
                Item('&Open', 'Ctrl+O',
                     'Load model or open new model from a MAD-X file.',
                     self.fileOpen,
                     QtGui.QStyle.SP_DialogOpenButton),
                Item('&Save', 'Ctrl+S',
                     'Save the current model (beam + twiss) to a file',
                     self.fileSave,
                     QtGui.QStyle.SP_DialogSaveButton),
                Separator,
                Item('&Quit', 'Ctrl+Q',
                     'Close window',
                     self.close,
                     QtGui.QStyle.SP_DialogCloseButton),
            ]),
            Menu('&View', [
                Item('&Python shell', 'Ctrl+P',
                     'Show a python shell',
                     self.viewShell),
            ]),
            Menu('&Help', [
                Item('About Mad&Qt', None,
                     'About the MadQt GUI application.',
                     self.helpAboutMadQt),
                Item('About &CPyMAD', None,
                     'About the cpymad python binding to MAD-X.',
                     self.helpAboutCPyMAD),
                Item('About MAD-&X', None,
                     'About the included MAD-X backend.',
                     self.helpAboutMadX),
            ]),
        ])

    def createControls(self):
        pass

    def createStatusBar(self):
        self.statusBar()

    #----------------------------------------
    # Menu actions
    #----------------------------------------

    def fileOpen(self):
        pass

    def fileSave(self):
        pass

    def viewShell(self):
        pass

    def helpAboutMadQt(self):
        """Show about dialog."""
        import madqt
        self._showAboutDialog(madqt)

    def helpAboutCPyMAD(self):
        """Show about dialog."""
        import cpymad
        self._showAboutDialog(cpymad)

    def helpAboutMadX(self):
        """Show about dialog."""
        import cpymad.madx
        self._showAboutDialog(cpymad.madx.metadata)

    def _showAboutDialog(self, module):
        import madqt.core.about as about
        info = about.VersionInfo(module)
        dialog = about.AboutDialog(info, self)
        dialog.show()
