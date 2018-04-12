"""
Main window component for madgui.
"""

import glob
import os
import logging
import time
from functools import partial

from madgui.qt import Qt, QtCore, QtGui
from madgui.core.base import Signal
from madgui.util.collections import Selection, Bool
from madgui.util.misc import SingleWindow, logfile_name, try_import
from madgui.util.qt import notifyCloseEvent, notifyEvent
from madgui.widget.dialog import Dialog
from madgui.widget.log import LogWindow, LogRecord

import madgui.online.control as control
import madgui.core.config as config
import madgui.core.menu as menu
import madgui.util.yaml as yaml


__all__ = [
    'MainWindow',
]


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
        self.context = {
            'frame': self,
        }
        self.options = options
        self.config = config.load(options['--config'])
        self.session_file = self.config.session_file
        self.model = None
        self.control = control.Control(self)
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
        runtime = self.config.get('runtime_path', [])
        runtime = [runtime] if isinstance(runtime, str) else runtime
        for path in runtime:
            os.environ['PATH'] += os.pathsep + os.path.abspath(path)
        self.folder = self.config.model_path
        config.number = self.config.number
        exec(self.config.onload, self.context)

    def session_data(self):
        return {
            'mainwindow': {
                'init_size': [self.size().width(), self.size().height()],
                'init_pos': [self.pos().x(), self.pos().y()],
            },
            'online_control': {
                'connect': self.control.is_connected(),
                'monitors': self.config.online_control['monitors'],
            },
            'model_path': self.folder,
            'load_default': self.model and self.model.filename,
            'number': self.config['number'],
        }

    def initUI(self):
        self.views = []
        self.setWindowTitle("madgui")
        self.createMenu()
        self.createControls()
        self.createStatusBar()
        self.configure()
        self.initPos()

    def initPos(self):
        self.resize(QtCore.QSize(*self.config.mainwindow.init_size))
        self.move(QtCore.QPoint(*self.config.mainwindow.init_pos))

    def loadDefault(self):
        filename = self.options['FILE'] or self.config.load_default
        if filename:
            self.loadFile(self.searchFile(filename))
        else:
            self.log.info('Welcome to madgui. Type <Ctrl>+O to open a file.')

    def createMenu(self):
        control = self.control
        Menu, Item, Separator = menu.Menu, menu.Item, menu.Separator
        menubar = self.menuBar()
        items = menu.extend(self, menubar, [
            Menu('&File', [
                Item('&Open', 'Ctrl+O',
                     'Load model or open new model from a MAD-X file.',
                     self.fileOpen,
                     QtGui.QStyle.SP_DialogOpenButton),
                Separator,
                Item('&Initial conditions', 'Ctrl+I',
                     'Modify the initial conditions, beam, and parameters.',
                     self.editInitialConditions.create),
                Item('&Load strengths', 'Ctrl+L',
                     'Execute MAD-X file in current context.',
                     self.execFile),
                Separator,
                Item('&Quit', 'Ctrl+Q',
                     'Close window.',
                     self.close,
                     QtGui.QStyle.SP_DialogCloseButton),
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
                Item('&Spin box', None,
                     'Display spinboxes for number input controls',
                     self.setSpinBox, checked=self.config.number.spinbox),
            ]),
            Menu('&Online control', [
                Item('&Disconnect', None,
                    'Disconnect online control interface',
                    control.disconnect,
                    enabled=control.is_connected),
                Separator,
                Item('&Read strengths', None,
                    'Read magnet strengths from the online database',
                    control.on_read_all,
                    enabled=control.has_sequence),
                Item('&Write strengths', None,
                    'Write magnet strengths to the online database',
                    control.on_write_all,
                    enabled=control.has_sequence),
                Item('Read &beam', None,
                    'Read beam settings from the online database',
                    control.on_read_beam,
                    enabled=control.has_sequence),
                Separator,
                Item('Show beam &monitors', None,
                    'Show beam monitor values (envelope/position)',
                    control.monitor_widget.create,
                    enabled=control.has_sequence),
                Separator,
                menu.Menu('&Orbit correction', [
                    Item('Optic &variation', 'Ctrl+V',
                        'Perform orbit correction via 2-optics method',
                        control.on_correct_optic_variation_method,
                        enabled=control.has_sequence),
                    Item('Multi &grid', 'Ctrl+G',
                        'Perform orbit correction via 2-grids method',
                        control.on_correct_multi_grid_method,
                        enabled=control.has_sequence),
                ]),
                Item('&Emittance measurement', 'Ctrl+E',
                    'Perform emittance measurement using at least 3 monitors',
                    control.on_emittance_measurement,
                    enabled=control.has_sequence),
                Separator,
                menu.Menu('&Settings', [
                    # TODO: dynamically fill by plugin
                    Item('&Jitter', None,
                        'Random Jitter for test interface',
                        control.toggle_jitter,
                        enabled=control.is_connected,
                        checked=True),
                ]),
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
        self.csys_menu = items[3]
        self.dc_action = self.csys_menu.actions()[0]

    def add_online_plugin(self, loader):
        if loader.check_avail():
            self.csys_menu.insertAction(self.dc_action, menu.Item(
                'Connect ' + loader.title, loader.hotkey,
                'Connect ' + loader.descr,
                partial(self.control.connect, loader),
                enabled=self.control.can_connect).action(self.menuBar()))
            if self.config.online_control.connect and \
                    not self.control.is_connected():
                self.control.connect(loader)

    dataReceived = Signal(object)

    def createControls(self):
        self.log_window = LogWindow()
        self.log_window.setup_logging(logging.DEBUG)
        self.dataReceived.connect(partial(self.log_window.recv_log, 'MADX'))

        QColor = QtGui.QColor
        self.log_window.highlight('SEND',     QColor(Qt.yellow).lighter(160))
        self.log_window.highlight('MADX',     QColor(Qt.lightGray))

        self.log_window.highlight('DEBUG',    QColor(Qt.blue).lighter(180))
        self.log_window.highlight('INFO',     QColor(Qt.green).lighter(150))
        self.log_window.highlight('WARNING',  QColor(Qt.yellow))
        self.log_window.highlight('ERROR',    QColor(Qt.red))
        self.log_window.highlight('CRITICAL', QColor(Qt.red))

        self.notebook = QtGui.QTabWidget()
        self.notebook.tabBar().hide()
        self.notebook.addTab(self.log_window, "Log")
        self.setCentralWidget(self.notebook)

    def createStatusBar(self):
        self.statusBar()

    def log_command(self, text):
        text = text.rstrip()
        self.logfile.write(text + '\n')
        self.logfile.flush()
        self.log_window.records.append(LogRecord(
            time.time(), 'SEND', text))

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

    def execFile(self):
        from madgui.widget.filedialog import getOpenFileName
        filters = [
            ("Strength files", "*.str"),
            ("All MAD-X files", "*.madx", "*.str", "*.seq"),
            ("All files", "*"),
        ]
        filename = getOpenFileName(
            self, 'Open MAD-X strengths file', self.folder, filters)
        if filename:
            self.model.madx.call(filename)
            self.model.twiss.invalidate()

    def fileSave(self):
        pass

    @SingleWindow.factory
    def editInitialConditions(self):
        from madgui.widget.params import TabParamTables, ParamTable
        from madgui.widget.elementinfo import EllipseWidget

        class InitEllipseWidget(EllipseWidget):
            def update(self): super().update(0)

        widget = TabParamTables([
            ('Twiss', ParamTable(self.model.get_twiss_ds())),
            ('Beam', ParamTable(self.model.get_beam_ds())),
            ('Globals', ParamTable(self.model.get_globals_ds())),
            ('Ellipse', InitEllipseWidget(self.model)),
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
        latview.setElements(self.model.elements,
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
            text=self.config.number.fmtspec)
        if not ok:
            return
        try:
            format(1.1, fmtspec)
        except ValueError:
            # TODO: show warning
            return
        self.config.number.fmtspec = fmtspec

    def setSpinBox(self):
        # TODO: sync with menu state
        self.config.number.spinbox = not self.config.number.spinbox

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
                            command_log=self.log_command,
                            stdout_log=self.dataReceived.emit))
        self.showTwiss()

    def setModel(self, model):
        if model is self.model:
            return
        self.destroyModel()
        self.model = model
        self.context['model'] = model

        if model is None:
            self.model_changed.emit()
            self.setWindowTitle("madgui")
            return

        self.context['madx'] = model.madx
        self.context['twiss'] = model.twiss.data
        exec(model.data.get('onload', ''), self.context)

        model.twiss.updated.connect(self.update_twiss)

        model.selection = Selection()
        model.box_group = InfoBoxGroup(self, model.selection)

        # This is required to make the thread exit (and hence allow the
        # application to close) by calling app.quit() on Ctrl-C:
        QtGui.qApp.aboutToQuit.connect(self.destroyModel)
        self.has_model.set(True)
        self.model_changed.emit()
        self.setWindowTitle(model.name)

    def destroyModel(self):
        if self.model is None:
            return
        self.model.twiss.updated.disconnect(self.update_twiss)
        self.has_model.set(False)
        del self.model.selection.elements[:]
        try:
            self.model.destroy()
        except IOError:
            # The connection may already be terminated in case MAD-X crashed.
            pass
        self.model = None
        self.context['model'] = None
        self.context['twiss'] = None
        self.logfile.close()

    def update_twiss(self):
        self.context['twiss'] = self.model.twiss.data

    def showTwiss(self, name=None):
        import madgui.plot.matplotlib as plt
        import madgui.plot.twissfigure as twissfigure

        model = self.model
        config = self.config.line_view

        # indicators require retrieving data for all elements which can be too
        # time consuming for large lattices:
        show_indicators = len(model.elements) < 500

        figure = plt.MultiFigure()
        plot = plt.PlotWidget(figure)

        scene = twissfigure.TwissFigure(figure, model, config)
        scene.show_indicators = show_indicators
        scene.set_graph(name or config.default_graph)
        scene.attach(plot)

        # for convenience when debugging:
        self.context.update({
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

    def graphs(self, name):
        return [scene for scene in self.views if scene.graph_name == name]

    def open_graph(self, name):
        if name in self.graphs(name):
            return
        if self.views:
            self.views[-1].set_graph('orbit')
        else:
            self.showTwiss(name)

    def _createShell(self):
        """Create a python shell widget."""
        import madgui.core.pyshell as pyshell
        self.shell = pyshell.create(self.context)
        dock = QtGui.QDockWidget()
        dock.setWidget(self.shell)
        dock.setWindowTitle("python shell")
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.shell.exit_requested.connect(dock.close)
        return dock

    def closeEvent(self, event):
        if self.session_file:
            self.save_session(self.session_file)
        # Terminate the remote session, otherwise `_readLoop()` may hang:
        self.destroyModel()
        event.accept()

    def save_session(self, filename):
        data = self.session_data()
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'wt') as f:
            yaml.safe_dump(data, f, default_flow_style=False)


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
        self.boxes[index].setWindowTitle(self.model.elements[el_id].node_name)

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
        dock.setWindowTitle("Element details: " + self.model.elements[el_id].node_name)
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
        box.window().setWindowTitle("Element details: " + self.model.elements[new_el_id].node_name)
