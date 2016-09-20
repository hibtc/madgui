# encoding: utf-8
"""
Main window component for MadQt.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import glob
import logging
import threading
import os

from six import text_type as unicode

from madqt.qt import QtCore, QtGui
from madqt.core.base import Object, Signal

import madqt.util.font as font
import madqt.core.config as config
import madqt.core.menu as menu


__all__ = [
    'MainWindow',
]


def savedict(filename, data):
    import numpy as np
    from madqt.core.unit import get_unit_label
    cols = list(data)
    body = list(data.values())
    for i, col in enumerate(body[:]):
        try:
            cols[i] += get_unit_label(col)
            body[i] = col.magnitude
        except AttributeError:
            pass
    np.savetxt(filename, np.array(body).T, header=' '.join(cols))


class MainWindow(QtGui.QMainWindow):

    #----------------------------------------
    # Basic setup
    #----------------------------------------

    def __init__(self, options, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.user_ns = {}
        self.options = options
        self.config = config.load(options['--config'])
        self.universe = None
        self.folder = self.config.get('model_path', '')
        self.initUI()
        # Defer `loadDefault` to avoid creation of a AsyncRead thread before
        # the main loop is entered: (Being in the mainloop simplifies
        # terminating the AsyncRead thread via the QApplication.aboutToQuit
        # signal. Without this, if the setup code excepts after creating the
        # thread the main loop will never be entered and thus aboutToQuit
        # never be emitted, even when pressing Ctrl+C.)
        QtCore.QTimer.singleShot(0, self.loadDefault)

    def initUI(self):
        self.createMenu()
        self.createControls()
        self.createStatusBar()

    def loadDefault(self):
        filename = self.options['FILE']
        if filename is None:
            filename = self.config.get('load_default')
        if filename:
            self.loadFile(self.searchFile(filename))

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
            Menu('&Edit', [
                Item('&TWISS initial conditions', 'Ctrl+T',
                     'Modify the initial conditions.',
                     self.editTwiss),
                Item('&Beam parameters', 'Ctrl+B',
                     'Change the beam parameters.',
                     self.editBeam),
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
                Item('About Q&t', None,
                     'About Qt.',
                     self.helpAboutQt),
            ]),
        ])

    def createControls(self):
        # Create an empty container as central widget in advance. For more
        # info, see the MainWindow.setCentralWidget method.
        widget = QtGui.QWidget()
        layout = QtGui.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def createStatusBar(self):
        self.statusBar()

    #----------------------------------------
    # Menu actions
    #----------------------------------------

    def fileOpen(self):
        filters = [
            ("Model files", "*.cpymad.yml", "*.pytao.yml"),
            ("MAD-X files", "*.madx", "*.str", "*.seq"),
            ("Bmad lattice", ".bmad", "*.lat"),
            ("All files", "*"),
        ]
        filename = getOpenFileName(
            self, 'Open file', self.folder, filters)
        if filename:
            self.loadFile(filename)

    def fileSave(self):
        pass

    def editTwiss(self):
        # TODO: inhibit multiple dialogs
        from madqt.widget.dialog import Dialog
        from madqt.widget.twissparams import TwissParamsWidget

        widget = TwissParamsWidget(self.universe.utool)
        widget.setData(self.universe.segment.twiss_args)

        dialog = Dialog(self)
        dialog.applied.connect(lambda: self.setTwiss(widget.data()))
        dialog.setExportWidget(widget, self.folder)
        dialog.show()

    def setTwiss(self, data):
        self.universe.segment.twiss_args = data

    def editBeam(self):
        # TODO: inhibit multiple dialogs
        from madqt.widget.dialog import Dialog
        from madqt.widget.beamparams import BeamParamsWidget

        widget = BeamParamsWidget(self.universe.utool)
        widget.setData(self.universe.segment.beam)

        dialog = Dialog(self)
        dialog.applied.connect(lambda: self.setBeam(widget.data()))
        dialog.setExportWidget(widget, self.folder)
        dialog.show()

    def setBeam(self, data):
        self.universe.segment.beam = data

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

    def helpAboutQt(self):
        QtGui.QMessageBox.aboutQt(self)

    def _showAboutDialog(self, module):
        import madqt.core.about as about
        info = about.VersionInfo(module)
        dialog = about.AboutDialog(info, self)
        dialog.show()

    #----------------------------------------
    # Update state
    #----------------------------------------

    def searchFile(self, path):
        if not os.path.exists(path) and not os.path.isabs(path) and self.folder:
            path = os.path.join(self.folder, path)
        if os.path.isdir(path):
            models = (glob.glob(os.path.join(path, '*.cpymad.yml')) +
                      glob.glob(os.path.join(path, '*.pytao.yml')) +
                      glob.glob(os.path.join(path, '*.init')))
            if models:
                path = models[0]
        if not os.path.isfile(path):
            raise OSError("File not found: {!r}".format(path))
        return path

    def loadFile(self, filename):
        """Load the specified model and show plot inside the main window."""
        if filename.endswith('.cpymad.yml'):
            from madqt.engine.madx import Universe
        elif filename.endswith('.pytao.yml'):
            from madqt.engine.tao import Universe
        else:
            raise NotImplementedError("Unsupported file format: {}"
                                      .format(filename))

        filename = os.path.abspath(filename)
        self.folder, _ = os.path.split(filename)
        self.setUniverse(Universe(filename))
        self.showTwiss()

    def setUniverse(self, universe):
        if universe is self.universe:
            return
        self.destroyUniverse()
        self.universe = universe
        self.user_ns['universe'] = universe
        self.user_ns['savedict'] = savedict
        if universe is None:
            return
        self._createLogTab()

        madx_log = AsyncRead(universe.remote_process.stdout)
        madx_log.dataReceived.connect(self._log_stream.write)

        # This is required to make the thread exit (and hence allow the
        # application to close) by calling app.quit() on Ctrl-C:
        QtGui.qApp.aboutToQuit.connect(self.destroyUniverse)

    def destroyUniverse(self):
        if self.universe is None:
            return
        try:
            self.universe.destroy()
        except IOError:
            # The connection may already be terminated in case MAD-X crashed.
            pass
        self.universe = None
        self.user_ns['universe'] = None

    def showTwiss(self):
        import madqt.plot.matplotlib as plot
        import madqt.plot.twissfigure as figure

        segment = self.universe.segment
        basename = 'env'
        config = self.config['line_view'].copy()
        config['matching'] = self.config['matching']

        figure = figure.TwissFigure(plot, segment, basename, config)
        figure.show_indicators = True
        widget = plot.PlotWidget(figure)
        self.universe.destroyed.connect(widget.close)
        self.universe.destroyed.connect(figure.remove)

        self.setMainWidget(widget)

    def setMainWidget(self, widget):
        """Set the central widget."""
        # On PyQt4, if the central widget is replaced after having created a
        # dock widget, the layout gets messed up (in this case the central
        # widget does not respect the preferred size hints). Therefore, we
        # have to just update its contents:
        layout = self.centralWidget().layout()
        layout.takeAt(0)            # safe to call on empty layouts
        layout.addWidget(widget)
        self.updateGeometry()

    def _createShell(self):
        """Create a python shell widget."""
        import madqt.core.pyshell as pyshell
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
        self.universe.destroyed.connect(dock.close)

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

    def _appendToLog(self, text):
        self._log_widget.appendPlainText(text.rstrip())

    def closeEvent(self, event):
        # Terminate the remote session, otherwise `_readLoop()` may hang:
        self.destroyUniverse()
        event.accept()


class AsyncRead(Object):

    """
    Write to a text control.
    """

    dataReceived = Signal(unicode)
    closed = Signal()

    def __init__(self, stream):
        super(AsyncRead, self).__init__()
        self.stream = stream
        self.thread = threading.Thread(target=self._readLoop)
        self.thread.start()

    def _readLoop(self):
        # The file iterator seems to be buffered:
        for line in iter(self.stream.readline, b''):
            try:
                self.dataReceived.emit(line.decode('utf-8'))
            except BaseException:
                break


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
