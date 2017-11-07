# encoding: utf-8
"""
Main window component for MadQt.
"""

# TODO: about dialogs for Bmad/pytao

from __future__ import absolute_import
from __future__ import unicode_literals

import glob
import os
import logging

from madqt.qt import Qt, QtCore, QtGui
from madqt.util.collections import Selection, Bool
from madqt.util.misc import Property
from madqt.util.qt import notifyCloseEvent
from madqt.widget.dialog import Dialog
from madqt.widget.log import LogWindow

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


def expand_ext(path, *exts):
    for ext in exts:
        if os.path.isfile(path+ext):
            return path+ext
    return path


class SingleWindow(Property):

    def _del(self):
        self.val.close()

    def _closed(self):
        super(SingleWindow, self)._del()

    def _new(self):
        window = super(SingleWindow, self)._new()
        notifyCloseEvent(window, self._closed)
        return window


class MainWindow(QtGui.QMainWindow):

    #----------------------------------------
    # Basic setup
    #----------------------------------------

    def __init__(self, options, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.has_workspace = Bool(False)
        self.user_ns = {
            'frame': self,
        }
        self.options = options
        self.config = config.load(options['--config'])
        self.workspace = None
        self.configure()
        self.initUI()
        # Defer `loadDefault` to avoid creation of a AsyncRead thread before
        # the main loop is entered: (Being in the mainloop simplifies
        # terminating the AsyncRead thread via the QApplication.aboutToQuit
        # signal. Without this, if the setup code excepts after creating the
        # thread the main loop will never be entered and thus aboutToQuit
        # never be emitted, even when pressing Ctrl+C.)
        self.log = logging.getLogger(__name__)
        QtCore.QTimer.singleShot(0, self.loadDefault)

    def configure(self):
        self.folder = self.config.get('model_path', '')
        align = {'left': Qt.AlignLeft, 'right': Qt.AlignRight}
        config.NumberFormat.align = align[self.config['number']['align']]
        config.NumberFormat.fmtspec = self.config['number']['fmtspec']
        config.NumberFormat.changed.emit()

    def initUI(self):
        self.createMenu()
        self.createControls()
        self.createStatusBar()
        self.resize(self.getInitSize())

    def getInitSize(self):
        if 'init_size' in self.config['mainwindow']:
            return QtCore.QSize(*self.config['mainwindow']['init_size'])
        screen = QtGui.QDesktopWidget().availableGeometry()
        return screen.size()*0.8

    def loadDefault(self):
        filename = self.options['FILE']
        if filename is None:
            filename = self.config.get('load_default')
        if filename:
            self.loadFile(self.searchFile(filename))
        else:
            self.log.info('Welcome to MadQt. Type <Ctrl>+O to open a file.')

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
                Item('&TWISS initial conditions', 'Ctrl+I',
                     'Modify the initial conditions.',
                     self.editTwiss),
                Item('&Beam parameters', 'Ctrl+B',
                     'Change the beam parameters.',
                     self.editBeam),
            ]),
            Menu('&View', [
                Item('Plo&t window', 'Ctrl+T',
                     'Open a new plot window.',
                     self.showTwiss),
                Item('&Python shell', 'Ctrl+P',
                     'Show a python shell.',
                     self.viewShell.toggle, checked=False),
                Item('&Floor plan', 'Ctrl+F',
                     'Show a 2D floor plan of the lattice.',
                     self.viewFloorPlan.toggle, checked=False),
            ]),
            Menu('&Settings', [
                Item('&Number format', None,
                     'Set the number format/precision used in dialogs',
                     self.setNumberFormat),
                Item('&Wheels', None,
                     'Display spinboxes for number input controls',
                     self.setSpinBox, checked=config.NumberFormat.spinbox),
            ]),
            Menu('&Help', [
                Item('About Mad&Qt', None,
                     'About the MadQt GUI application.',
                     self.helpAboutMadQt.create),
                Item('About &CPyMAD', None,
                     'About the cpymad python binding to MAD-X.',
                     self.helpAboutCPyMAD.create),
                Item('About MAD-&X', None,
                     'About the included MAD-X backend.',
                     self.helpAboutMadX.create),
                Item('About Q&t', None,
                     'About Qt.',
                     self.helpAboutQt),
            ]),
        ])

        import madqt.online.control as control
        self.control = control.Control(self, menubar)

    def createControls(self):
        self.log_window = LogWindow(self)
        self.log_window.setup_logging()
        self.setCentralWidget(self.log_window)

    def createStatusBar(self):
        self.statusBar()

    #----------------------------------------
    # Menu actions
    #----------------------------------------

    def fileOpen(self):
        from madqt.util.filedialog import getOpenFileName
        filters = [
            ("Model files", "*.cpymad.yml", "*.pytao.yml"),
            ("MAD-X files", "*.madx", "*.str", "*.seq"),
            ("Bmad lattice", "*.bmad", "*.lat", "*.init"),
            ("All files", "*"),
        ]
        filename = getOpenFileName(
            self, 'Open file', self.folder, filters)
        if filename:
            self.loadFile(filename)

    def fileSave(self):
        pass

    init_tab = None

    def editTwiss(self):
        # TODO: rework window management, switch tab if dialog exists
        self.init_tab = 'twiss'
        return self.editInitialConditions.create()

    def editBeam(self):
        # TODO: rework window management, switch tab if dialog exists
        self.init_tab = 'beam'
        return self.editInitialConditions.create()

    @SingleWindow.factory
    def editInitialConditions(self):
        from madqt.widget.params import TabParamTables

        datastore = self.workspace.segment.get_init_ds()
        index = next((i for i, l in enumerate(datastore.substores)
                      if l == self.init_tab), 0)

        widget = TabParamTables(datastore, index=index)
        widget.update()

        dialog = Dialog(self)
        dialog.setExportWidget(widget, self.folder)
        dialog.setWindowTitle("Initial conditions")
        dialog.show()
        return dialog

    @SingleWindow.factory
    def viewShell(self):
        return self._createShell()

    @SingleWindow.factory
    def viewFloorPlan(self):
        from madqt.widget.floor_plan import LatticeFloorPlan
        latview = LatticeFloorPlan()
        latview.setElements(self.workspace.utool,
                            self.workspace.segment.elements,
                            self.workspace.segment.survey(),
                            self.workspace.selection)
        dock = Dialog(self)
        dock.setWidget(latview)
        dock.setWindowTitle("2D floor plan")
        dock.show()
        return dock

    @SingleWindow.factory
    def viewMatchDialog(self):
        from madqt.widget.match import MatchWidget
        widget = MatchWidget(self.workspace.segment.get_matcher())
        dialog = Dialog(self)
        dialog.setWidget(widget, tight=True)
        dialog.setWindowTitle("Matching constraints.")
        dialog.show()
        return dialog

    def setNumberFormat(self):
        fmtspec, ok = QtGui.QInputDialog.getText(
            self, "Set number format", "Number format:",
            text=config.NumberFormat.fmtspec)
        if not ok:
            return
        try:
            format(1.1, fmtspec)
        except ValueError:
            # TODO: show warning
            return
        config.NumberFormat.fmtspec = fmtspec
        config.NumberFormat.changed.emit()

    def setSpinBox(self):
        # TODO: sync with menu state
        config.NumberFormat.spinbox = not config.NumberFormat.spinbox
        config.NumberFormat.changed.emit()

    @SingleWindow.factory
    def helpAboutMadQt(self):
        """Show about dialog."""
        import madqt
        return self._showAboutDialog(madqt)

    @SingleWindow.factory
    def helpAboutCPyMAD(self):
        """Show about dialog."""
        import cpymad
        return self._showAboutDialog(cpymad)

    @SingleWindow.factory
    def helpAboutMadX(self):
        """Show about dialog."""
        import cpymad.madx
        return self._showAboutDialog(cpymad.madx.metadata)

    def helpAboutQt(self):
        QtGui.QMessageBox.aboutQt(self)

    def _showAboutDialog(self, module):
        import madqt.core.about as about
        info = about.VersionInfo(module)
        dialog = about.AboutDialog(info, self)
        dialog.show()
        return dialog

    #----------------------------------------
    # Update state
    #----------------------------------------

    known_extensions = ['.cpymad.yml', '.pytao.yml',
                        '.init', '.lat', '.madx', '.bmad']

    def searchFile(self, path):
        for path in [path, os.path.join(self.folder or '.', path)]:
            if os.path.isdir(path):
                models = (glob.glob(os.path.join(path, '*.cpymad.yml')) +
                          glob.glob(os.path.join(path, '*.pytao.yml')) +
                          glob.glob(os.path.join(path, '*.init')))
                if models:
                    path = models[0]
            path = expand_ext(path, '', *self.known_extensions)
            if os.path.isfile(path):
                return path
        raise OSError("File not found: {!r}".format(path))

    def loadFile(self, filename):
        """Load the specified model and show plot inside the main window."""
        engine_exts = {
            'madqt.engine.madx': ('.cpymad.yml', '.madx', '.str', '.seq'),
            'madqt.engine.tao': ('.pytao.yml', '.bmad', '.lat', '.init'),
        }

        for modname, exts in engine_exts.items():
            if any(map(filename.endswith, exts)):
                module = __import__(modname, None, None, '*')
                Workspace = module.Workspace
                break
        else:
            raise NotImplementedError("Unsupported file format: {}"
                                      .format(filename))

        filename = os.path.abspath(filename)
        self.folder, _ = os.path.split(filename)
        self.log.info('Loading {}'.format(filename))
        self.setWorkspace(Workspace(filename, self.config))
        self.showTwiss()

    def setWorkspace(self, workspace):
        if workspace is self.workspace:
            return
        self.destroyWorkspace()
        self.workspace = workspace
        self.user_ns['workspace'] = workspace
        self.user_ns['savedict'] = savedict
        if workspace is None:
            return

        workspace.selection = Selection()
        workspace.box_group = InfoBoxGroup(self, workspace.selection)

        self.log_window.async_reader(
            workspace.backend_title,
            workspace.remote_process.stdout)

        # This is required to make the thread exit (and hence allow the
        # application to close) by calling app.quit() on Ctrl-C:
        QtGui.qApp.aboutToQuit.connect(self.destroyWorkspace)
        self.has_workspace.value = True

    def destroyWorkspace(self):
        if self.workspace is None:
            return
        self.has_workspace.value = False
        del self.workspace.selection.elements[:]
        try:
            self.workspace.destroy()
        except IOError:
            # The connection may already be terminated in case MAD-X crashed.
            pass
        self.workspace = None
        self.user_ns['workspace'] = None

    def showTwiss(self, name=None):
        import madqt.plot.matplotlib as plt
        import madqt.plot.twissfigure as twissfigure

        segment = self.workspace.segment
        config = self.config['line_view'].copy()
        config['matching'] = self.config['matching']

        # indicators require retrieving data for all elements which can be too
        # time consuming for large lattices:
        show_indicators = len(segment.elements) < 500

        figure = plt.MultiFigure()
        plot = plt.PlotWidget(figure)

        scene = twissfigure.TwissFigure(figure, segment, config)
        scene.show_indicators = show_indicators
        scene.graph_name = name or config['default_graph']
        scene.attach(plot)
        scene.plot()

        # for convenience when debugging:
        self.user_ns.update({
            'plot': plot,
            'figure': figure.backend_figure,
            'canvas': plot.canvas,
            'scene': scene,
        })

        menubar = QtGui.QMenuBar()
        select = twissfigure.PlotSelector(scene)
        widget = Dialog(self)
        widget.setWidget([select, plot])
        widget.layout().setMenuBar(menubar)
        widget.resize(self.size().width(), widget.sizeHint().height())
        widget.show()

        self.workspace.destroyed.connect(widget.close)
        self.workspace.destroyed.connect(scene.remove)

        def toggleShareAxes():
            scene.figure.share_axes = not scene.figure.share_axes
            scene.relayout()
            scene.plot()

        Menu, Item, Separator = menu.Menu, menu.Item, menu.Separator
        menu.extend(widget, menubar, [
            Menu('&View', [
                Item('&Shared plot', 'Ctrl+M',
                     'Plot all curves into the same plot - more compact format.',
                     toggleShareAxes, checked=False),
            ]),
        ])
        return scene

    def _createShell(self):
        """Create a python shell widget."""
        import madqt.core.pyshell as pyshell
        self.shell = pyshell.create(self.user_ns)
        dock = QtGui.QDockWidget()
        dock.setWidget(self.shell)
        dock.setWindowTitle("python shell")
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.shell.exit_requested.connect(dock.close)
        return dock

    def closeEvent(self, event):
        # Terminate the remote session, otherwise `_readLoop()` may hang:
        self.destroyWorkspace()
        event.accept()


class InfoBoxGroup(object):

    def __init__(self, mainwindow, selection):
        """Add toolbar tool to panel and subscribe to capture events."""
        super(InfoBoxGroup, self).__init__()
        self.mainwindow = mainwindow
        self.selection = selection
        self.boxes = [self.create_info_box(elem)
                      for elem in selection.elements]
        selection.elements.insert_notify.connect(self._insert)
        selection.elements.delete_notify.connect(self._delete)
        selection.elements.modify_notify.connect(self._modify)

    # keep info boxes in sync with current selection

    def _insert(self, index, el_id):
        self.boxes.insert(index, self.create_info_box(el_id))

    def _delete(self, index):
        if self.boxes[index].isVisible():
            self.boxes[index].parent().close()
        del self.boxes[index]

    def _modify(self, index, el_id):
        self.boxes[index].el_id = el_id
        self.boxes[index].setWindowTitle(self.segment.elements[el_id]['name'])

    # utility methods

    @property
    def segment(self):
        return self.mainwindow.workspace.segment

    def _on_close_box(self, box):
        el_id = box.el_id
        if el_id in self.selection.elements:
            self.selection.elements.remove(el_id)

    def set_active_box(self, box):
        self.selection.top = self.boxes.index(box)
        box.raise_()

    def create_info_box(self, el_id):
        from madqt.widget.elementinfo import ElementInfoBox
        from madqt.util.qt import notifyCloseEvent, notifyEvent
        info = ElementInfoBox(self.segment, el_id)
        dock = Dialog(self.mainwindow)
        dock.setExportWidget(info, None)
        dock.setWindowTitle(u"Element details: " + self.segment.elements[el_id]['name'])
        notifyCloseEvent(dock, lambda: self._on_close_box(info))
        notifyEvent(info, 'focusInEvent', lambda event: self.set_active_box(info))

        dock.show()
        dock.raise_()
        self.segment.workspace.destroyed.connect(dock.close)

        return info
