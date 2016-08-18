# encoding: utf-8
"""
Main window component for MadQt.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import logging
import threading

from madqt.qt import QtCore, QtGui

import madqt.util.filedialog as filedialog
import madqt.util.font as font
import madqt.core.config as config
import madqt.core.menu as menu
import madqt.engine.madx as madx


__all__ = [
    'MainWindow',
]


class MainWindow(QtGui.QMainWindow):

    #----------------------------------------
    # Basic setup
    #----------------------------------------

    def __init__(self, options, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.options = options
        self.config = config.load(options['--config'])
        self.universe = None
        self.folder = self.config.get('model_path', '')
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
                     'Save the current model (beam + twiss) to a file.',
                     self.fileSave,
                     QtGui.QStyle.SP_DialogSaveButton),
                Separator,
                Item('&Quit', 'Ctrl+Q',
                     'Close window.',
                     self.close,
                     QtGui.QStyle.SP_DialogCloseButton),
            ]),
            Menu('&View', [
                Item('&Python shell', 'Ctrl+P',
                     'Show a python shell.',
                     self.viewShell),
                Item('&Log window', 'Ctrl+L',
                     'Show a log window.',
                     self.viewLog),
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
        filters = filedialog.make_filter([
            ("Model files", "*.cpymad.yml"),
            ("MAD-X files", "*.madx", "*.str", "*.seq"),
            ("All files", "*"),
        ])
        filename = QtGui.QFileDialog.getOpenFileName(
            self, 'Open file', self.folder, filters)
        if not filename:
            return
        self.setUniverse(madx.Universe())
        self.universe.load(filename)
        self.showTwiss()

    def fileSave(self):
        pass

    def viewShell(self):
        self._createShell()

    def viewLog(self):
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

    #----------------------------------------
    # Update state
    #----------------------------------------

    def setUniverse(self, universe):
        if universe is self.universe:
            return
        self.destroyUniverse()
        self.universe = universe
        if universe is None:
            return
        self._createLogTab()
        threading.Thread(target=self._read_stream,
                         args=(universe.remote_process.stdout,)).start()

    def destroyUniverse(self):
        if self.universe is None:
            return
        try:
            self.universe.destroy()
        except IOError:
            # The connection may already be terminated in case MAD-X crashed.
            pass
        self.universe = None

    def showTwiss(self):
        import madqt.plot.matplotlib as plot
        figure = plot.TwissFigure.create(self.universe, self, 'env')
        figure.show_indicators = True
        widget = plot.PlotWidget(figure)
        status = plot.UpdateStatusBar(self, figure)
        self.setCentralWidget(widget)

    def _createShell(self):
        """Create a python shell widget."""
        import madqt.core.pyshell as pyshell
        self.user_ns = {}
        self.shell = pyshell.create(self.user_ns)
        dock = QtGui.QDockWidget()
        dock.setWidget(self.shell)
        dock.setWindowTitle("python shell")
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, dock)
        self.shell.exit_requested.connect(dock.close)

    def _createLogTab(self):
        text = QtGui.QPlainTextEdit()
        text.setFont(font.monospace())
        text.setReadOnly(True)
        dock = QtGui.QDockWidget()
        dock.setWidget(text)
        dock.setWindowTitle("MAD-X output")
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, dock)
        # TODO: MAD-X log should be separate from basic logging
        self._basicConfig(text, logging.INFO,
                          '%(asctime)s %(levelname)s %(name)s: %(message)s',
                          '%H:%M:%S')

    def _basicConfig(self, widget, level, fmt, datefmt=None):
        """Configure logging."""
        stream = TextCtrlStream(widget)
        root = logging.RootLogger(level)
        manager = logging.Manager(root)
        formatter = logging.Formatter(fmt, datefmt)
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        root.addHandler(handler)
        # store member variables:
        self._log_widget = widget
        self._log_stream = stream
        self._log_manager = manager

    def _read_stream(self, stream):
        # The file iterator seems to be buffered:
        for line in iter(stream.readline, b''):
            try:
                self._log_stream.write(line)
            except:
                break

    def closeEvent(self, event):
        # Terminate the remote session, otherwise `_read_stream()` may hang:
        self.destroyUniverse()
        event.accept()


class TextCtrlStream(object):

    """
    Write to a text control.
    """

    def __init__(self, ctrl):
        """Set text control."""
        self._ctrl = ctrl

    def write(self, text):
        """Append text."""
        self._ctrl.appendPlainText(text.rstrip())
