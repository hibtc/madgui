"""
Main window component for madgui.
"""

import glob
import os
import logging
from functools import partial

from madgui.qt import Qt, QtCore, QtGui
from madgui.core.base import Signal
from madgui.util.collections import Selection, Bool
from madgui.util.misc import SingleWindow, logfile_name, try_import
from madgui.util.qt import notifyCloseEvent, notifyEvent
from madgui.widget.dialog import Dialog
from madgui.widget.log import LogWindow

import madgui.core.config as config
import madgui.core.menu as menu


__all__ = [
    'MainWindow',
]


def savedict(filename, data):
    import numpy as np
    from madgui.core.unit import get_unit_label
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


class MainWindow(QtGui.QMainWindow):

    model_changed = Signal()

    #----------------------------------------
    # Basic setup
    #----------------------------------------

    def __init__(self, options, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_model = Bool(False)
        self.user_ns = {
            'frame': self,
        }
        self.options = options
        self.config = config.load(options['--config'])
        self.model = None
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
        config.NumberFormat.spinbox = self.config['number']['spinbox']
        config.NumberFormat.changed.emit()

    def initUI(self):
        self.views = []
        self.setWindowTitle("madgui")
        self.createMenu()
        self.createControls()
        self.createStatusBar()
        self.initPos()

    def initPos(self):
        if 'init_size' in self.config['mainwindow']:
            size = QtCore.QSize(*self.config['mainwindow']['init_size'])
        else:
            size = QtGui.QDesktopWidget().availableGeometry() * 0.8
        self.resize(size)
        if 'init_pos' in self.config['mainwindow']:
            self.move(QtCore.QPoint(*self.config['mainwindow']['init_pos']))

    def loadDefault(self):
        filename = self.options['FILE']
        if filename is None:
            filename = self.config.get('load_default')
        if filename:
            self.loadFile(self.searchFile(filename))
        else:
            self.log.info('Welcome to madgui. Type <Ctrl>+O to open a file.')

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
                Item('&Magnet strengths', 'Ctrl+M',
                     'Change globals.',
                     self.editGlobals),
            ]),
            Menu('&View', [
                Item('Plo&t window', 'Ctrl+T',
                     'Open a new plot window.',
                     self.showTwiss),
                Item('&Python shell', 'Ctrl+P',
                     'Show a python shell.',
                     self.viewShell.toggle,
                     checked=self.viewShell.holds_value),
                Item('&Floor plan', 'Ctrl+F',
                     'Show a 2D floor plan of the lattice.',
                     self.viewFloorPlan.toggle,
                     checked=self.viewFloorPlan.holds_value),
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
                     'About the madgui GUI application.',
                     self.helpAboutMadGUI.create),
                try_import('cpymad') and
                Item('About &CPyMAD', None,
                     'About the cpymad python binding to MAD-X.',
                     self.helpAboutCPyMAD.create),
                try_import('cpymad') and
                Item('About MAD-&X', None,
                     'About the included MAD-X backend.',
                     self.helpAboutMadX.create),
                Item('About Q&t', None,
                     'About Qt.',
                     self.helpAboutQt),
            ]),
        ])

        import madgui.online.control as control
        self.control = control.Control(self, menubar)

    def createControls(self):
        self.log_window = LogWindow()
        self.log_window.setup_logging()
        self.cmd_window = QtGui.QPlainTextEdit()
        self.notebook = QtGui.QTabWidget()
        self.notebook.addTab(self.log_window, "Log")
        self.notebook.addTab(self.cmd_window, "Commands")
        self.setCentralWidget(self.notebook)

    def createStatusBar(self):
        self.statusBar()

    def log_command(self, text):
        text = text.rstrip()
        self.logfile.write(text + '\n')
        self.logfile.flush()
        self.cmd_window.appendPlainText(text)

    #----------------------------------------
    # Menu actions
    #----------------------------------------

    def fileOpen(self):
        from madgui.widget.filedialog import getOpenFileName
        filters = [
            ("Model files", "*.cpymad.yml"),
            ("MAD-X files", "*.madx", "*.str", "*.seq"),
            ("All files", "*"),
        ]
        filename = getOpenFileName(
            self, 'Open file', self.folder, filters)
        if filename:
            self.loadFile(filename)

    def fileSave(self):
        pass

    def editTwiss(self):
        widget = self.editInitialConditions.create()
        widget.activate_tab('twiss')

    def editBeam(self):
        widget = self.editInitialConditions.create()
        widget.activate_tab('beam')

    def editGlobals(self):
        widget = self.editInitialConditions.create()
        widget.activate_tab('globals')

    @SingleWindow.factory
    def editInitialConditions(self):
        from madgui.widget.params import TabParamTables, ParamTable

        widget = TabParamTables([
            ('Beam', ParamTable(self.model.get_beam_ds())),
            ('Twiss', ParamTable(self.model.get_twiss_ds())),
            ('Globals', ParamTable(self.model.get_globals_ds())),
        ])
        widget.update()

        dialog = Dialog(self)
        dialog.setExportWidget(widget, self.folder)
        dialog.setWindowTitle("Initial conditions")
        dialog.show()
        return widget

    @SingleWindow.factory
    def viewShell(self):
        return self._createShell()

    @SingleWindow.factory
    def viewFloorPlan(self):
        from madgui.widget.floor_plan import LatticeFloorPlan, Selector
        latview = LatticeFloorPlan()
        latview.setElements(self.model.utool,
                            self.model.elements,
                            self.model.survey(),
                            self.model.selection)
        selector = Selector(latview)
        dock = Dialog(self)
        dock.setWidget([latview, selector], tight=True)
        dock.setWindowTitle("2D floor plan")
        dock.show()
        return dock

    @SingleWindow.factory
    def viewMatchDialog(self):
        from madgui.widget.match import MatchWidget
        widget = MatchWidget(self.model.get_matcher())
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
    def helpAboutMadGUI(self):
        """Show about dialog."""
        import madgui
        return self._showAboutDialog(madgui)

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
        import madgui.core.about as about
        info = about.VersionInfo(module)
        dialog = about.AboutDialog(info, self)
        dialog.show()
        return dialog

    #----------------------------------------
    # Update state
    #----------------------------------------

    known_extensions = ['.cpymad.yml', '.init', '.lat', '.madx']

    def searchFile(self, path):
        for path in [path, os.path.join(self.folder or '.', path)]:
            if os.path.isdir(path):
                models = (glob.glob(os.path.join(path, '*.cpymad.yml')) +
                          glob.glob(os.path.join(path, '*.init')))
                if models:
                    path = models[0]
            path = expand_ext(path, '', *self.known_extensions)
            if os.path.isfile(path):
                return path
        raise OSError("File not found: {!r}".format(path))

    def loadFile(self, filename):
        """Load the specified model and show plot inside the main window."""
        exts = ('.cpymad.yml', '.madx', '.str', '.seq')
        if not any(map(filename.endswith, exts)):
            raise NotImplementedError("Unsupported file format: {}"
                                      .format(filename))
        from madgui.core.model import Model
        self.destroyModel()
        filename = os.path.abspath(filename)
        self.folder, name = os.path.split(filename)
        base, ext = os.path.splitext(name)
        logfile = logfile_name(self.folder, base, '.commands.madx')
        self.logfile = open(logfile, 'wt')
        self.log.info('Loading {}'.format(filename))
        self.log.info('Logging commands to: {}'.format(logfile))
        self.setModel(Model(filename, self.config,
                            command_log=self.log_command))
        self.showTwiss()

    def setModel(self, model):
        if model is self.model:
            return
        self.destroyModel()
        self.model = model
        self.user_ns['model'] = model
        self.user_ns['savedict'] = savedict

        if model is None:
            self.model_changed.emit()
            self.setWindowTitle("madgui")
            return

        self.user_ns['madx'] = model.madx
        self.user_ns['twiss'] = model.twiss.data

        model.twiss.updated.connect(self.update_twiss)

        model.selection = Selection()
        model.box_group = InfoBoxGroup(self, model.selection)

        self.log_window.async_reader(
            model.backend_title,
            model.remote_process.stdout)

        # This is required to make the thread exit (and hence allow the
        # application to close) by calling app.quit() on Ctrl-C:
        QtGui.qApp.aboutToQuit.connect(self.destroyModel)
        self.has_model.value = True
        self.model_changed.emit()
        self.setWindowTitle(model.name)

    def destroyModel(self):
        if self.model is None:
            return
        self.model.twiss.updated.disconnect(self.update_twiss)
        self.has_model.value = False
        del self.model.selection.elements[:]
        try:
            self.model.destroy()
        except IOError:
            # The connection may already be terminated in case MAD-X crashed.
            pass
        self.model = None
        self.user_ns['model'] = None
        self.user_ns['twiss'] = None
        self.logfile.close()

    def update_twiss(self):
        self.user_ns['twiss'] = self.model.twiss.data

    def showTwiss(self, name=None):
        import madgui.plot.matplotlib as plt
        import madgui.plot.twissfigure as twissfigure

        model = self.model
        config = self.config['line_view'].copy()
        config['matching'] = self.config['matching']

        # indicators require retrieving data for all elements which can be too
        # time consuming for large lattices:
        show_indicators = len(model.elements) < 500

        figure = plt.MultiFigure()
        plot = plt.PlotWidget(figure)

        scene = twissfigure.TwissFigure(figure, model, config)
        scene.show_indicators = show_indicators
        scene.set_graph(name or config['default_graph'])
        scene.attach(plot)

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
        widget.setWidget([select, plot], tight=True)
        widget.layout().setMenuBar(menubar)
        widget.resize(self.size().width(), widget.sizeHint().height())
        widget.show()
        def update_window_title():
            widget.setWindowTitle("{1} ({0})".format(
                self.model.name, scene.graph_name))
        scene.graph_changed.connect(update_window_title)
        update_window_title()

        self.model.destroyed.connect(widget.close)

        def destroyed():
            if scene in self.views:
                scene.destroy()
                self.views.remove(scene)

        notifyCloseEvent(widget, destroyed)

        def toggleShareAxes():
            scene.figure.share_axes = not scene.figure.share_axes
            scene.relayout()

        def toggleIndicators():
            scene.show_indicators = not scene.show_indicators

        Menu, Item, Separator = menu.Menu, menu.Item, menu.Separator
        menu.extend(widget, menubar, [
            Menu('&View', [
                # TODO: dynamic checked state
                Item('&Shared plot', 'Ctrl+M',
                     'Plot all curves into the same plot - more compact format.',
                     toggleShareAxes, checked=False),
                # TODO: dynamic checked state
                Item('Element &indicators', None,
                     'Show element indicators',
                     toggleIndicators, checked=show_indicators),
                Item('Manage curves', None,
                     'Select which data sets are shown',
                     scene._curveManager.toggle,
                     checked=scene._curveManager.holds_value),
            ]),
        ])
        self.views.append(scene)
        return scene

    def open_graph(self, name):
        if name in (scene.graph_name for scene in self.views):
            return
        if self.views:
            self.views[-1].set_graph('orbit')
        else:
            self.showTwiss(name)

    def _createShell(self):
        """Create a python shell widget."""
        import madgui.core.pyshell as pyshell
        self.shell = pyshell.create(self.user_ns)
        dock = QtGui.QDockWidget()
        dock.setWidget(self.shell)
        dock.setWindowTitle("python shell")
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.shell.exit_requested.connect(dock.close)
        return dock

    def closeEvent(self, event):
        # Terminate the remote session, otherwise `_readLoop()` may hang:
        self.destroyModel()
        event.accept()


class InfoBoxGroup:

    def __init__(self, mainwindow, selection):
        """Add toolbar tool to panel and subscribe to capture events."""
        super().__init__()
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
        self.boxes[index].setWindowTitle(self.model.elements[el_id].Name)

    # utility methods

    @property
    def model(self):
        return self.mainwindow.model

    def _on_close_box(self, box):
        el_id = box.el_id
        if el_id in self.selection.elements:
            self.selection.elements.remove(el_id)

    def set_active_box(self, box):
        self.selection.top = self.boxes.index(box)
        box.raise_()

    def create_info_box(self, el_id):
        from madgui.widget.elementinfo import ElementInfoBox
        info = ElementInfoBox(self.model, el_id)
        dock = Dialog(self.mainwindow)
        dock.setExportWidget(info, None)
        dock.setWindowTitle("Element details: " + self.model.elements[el_id].Name)
        notifyCloseEvent(dock, lambda: self._on_close_box(info))
        notifyEvent(info, 'focusInEvent', lambda event: self.set_active_box(info))

        dock.show()
        dock.raise_()
        self.model.destroyed.connect(dock.close)

        info.changed_element.connect(partial(self._changed_box_element, info))
        return info

    def _changed_box_element(self, box):
        box_index = self.boxes.index(box)
        new_el_id = box.el_id
        old_el_id = self.selection.elements[box_index]
        if new_el_id != old_el_id:
            self.selection.elements[box_index] = new_el_id
            box.window().setWindowTitle("Element details: " + self.model.elements[new_el_id].Name)
