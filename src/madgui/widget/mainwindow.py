"""
Main window component for madgui.
"""

__all__ = [
    'MainWindow',
]

import os
import logging
import subprocess
import time
from functools import partial

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QKeySequence
from PyQt5.QtWidgets import (
    QInputDialog, QMainWindow, QMessageBox, QStyle, QApplication)

from madgui.util.signal import Signal
from madgui.util.qt import notifyEvent, SingleWindow, load_ui
from madgui.util.undo import UndoStack
from madgui.widget.dialog import Dialog
from madgui.widget.log import LogRecord

import madgui.util.menu as menu


class MainWindow(QMainWindow):

    ui_file = 'mainwindow.ui'

    # Basic setup

    def __init__(self, session, *args, **kwargs):
        super().__init__(*args, **kwargs)
        load_ui(self, __package__, self.ui_file)
        session.model_args = self.model_args
        self.session = session
        self.config = session.config
        self.control = session.control
        self.model = session.model
        self.user_ns = session.user_ns
        self.exec_folder = self.config.exec_folder
        self.str_folder = self.config.str_folder
        self.model.changed2.connect(self._on_model_changed)
        self.initUI()
        logging.info('Welcome to madgui. Type <Ctrl>+O to open a file.')

    @property
    def folder(self):
        return self.session.folder

    def session_data(self):
        open_plot_windows = list(map(self._save_plot_window, self.views))
        return {
            'mainwindow': {
                'init_size': [self.size().width(), self.size().height()],
                'init_pos': [self.pos().x(), self.pos().y()],
                'font_size': self.font().pointSize(),
            },
            'logging': {
                'enable': self.logWidget.logging_enabled,
                'level': self.logWidget.loglevel,
                'maxlen': self.logWidget.maxlen,
                'times': {
                    'enable': self.logWidget.infobar.show_time,
                    'format': self.logWidget.infobar.time_format,
                },
                'madx': {
                    'in': self.logWidget.enabled('SEND'),
                    'out': self.logWidget.enabled('MADX'),
                },
            },
            'exec_folder': self.exec_folder,
            'str_folder': self.str_folder,
            'plot_windows': open_plot_windows + self.config.plot_windows,
            'interpolate': self.config.interpolate,
        }

    def initUI(self):
        self.views = []
        self.createMenu()
        self.createControls()
        self.resize(*self.config.mainwindow.init_size)
        self.move(*self.config.mainwindow.init_pos)
        if self.config.mainwindow.get('font_size'):
            self.setFontSize(self.config.mainwindow.font_size)

    def createMenu(self):
        control = self.control
        Menu, Item, Separator = menu.Menu, menu.Item, menu.Separator
        menubar = self.menuBar()
        items = menu.extend(self, menubar, [
            Menu('&Model', [
                Item('&Open', 'Ctrl+O',
                     'Load model or open new model from a MAD-X file.',
                     self.fileOpen,
                     QStyle.SP_DialogOpenButton),
                Separator,
                Item('&Initial conditions', 'Ctrl+I',
                     'Modify the initial conditions, beam, and parameters.',
                     self.editInitialConditions.create),
                Separator,
                Item('&Execute MAD-X file', 'Ctrl+E',
                     'Execute MAD-X file in current context.',
                     self.execFile),
                Separator,
                Item('&Revert sequence', None,
                     'Reverse current sequence from back to front '
                     '(experimental). Does not work with all element types.',
                     self.reverseSequence),
                Separator,
                Item('&Quit', 'Ctrl+Q',
                     'Close window.',
                     self.close,
                     QStyle.SP_DialogCloseButton),
            ]),
            Menu('&View', [
                Item('Plo&t window', 'Ctrl+T',
                     'Open a new plot window.',
                     self.showTwiss),
                Item('&Python shell', 'Ctrl+P',
                     'Show a python shell.',
                     self.viewShell),
                Item('&Floor plan', 'Ctrl+F',
                     'Show a 2D floor plan of the lattice.',
                     self.viewFloorPlan),
                Separator,
                Item('&Refresh', 'F5',
                     'Redo TWISS and refresh plot.',
                     self.refreshTwiss),
            ]),
            Menu('&Export', [
                Item('&Strengths', None,
                     'Export magnet strengths.',
                     self.saveStrengths),
                Item('&Beam', None,
                     'Export beam settings.',
                     self.saveBeam),
                Item('&Twiss && orbit', None,
                     'Export initial twiss parameters.',
                     self.saveTwiss),
                Separator,
                Item('Save MAD-X &commands', None,
                     'Export all MAD-X commands to a file.',
                     self.saveCommands),
            ]),
            Menu('&Import', [
                Item('&Strengths', None,
                     'Load .str file (simplified syntax).',
                     self.loadStrengths),
                Item('&Beam', None,
                     'Import beam settings.',
                     self.loadBeam),
                Item('&Twiss && orbit', None,
                     'Import initial twiss parameters.',
                     self.loadTwiss),
            ]),
            Menu('&Settings', [
                Item('&Number format', None,
                     'Set the number format/precision used in dialogs',
                     self.setNumberFormat),
                Item('&Spin box', None,
                     'Display spinboxes for number input controls',
                     self.toggleSpinBox, checked=self.config.number.spinbox),
                Separator,
                Item('&Interpolation points', None,
                     'Set number of data points.',
                     self.setInterpolate),
                Item('&Log size limit', None,
                     'Set number of log entries.',
                     self.setLogSize),
                Separator,
                Item('&Increase font size', QKeySequence.ZoomIn,
                     'Increase font size',
                     self.increaseFontSize),
                Item('&Decrease font size', QKeySequence.ZoomOut,
                     'Decrease font size',
                     self.decreaseFontSize),
            ]),
            Menu('&Online control', [
                Item('&Connect', None,
                     'Connect to the online backend',
                     control.connect,
                     enabled=control.can_connect),
                Item('&Disconnect', None,
                     'Disconnect online control interface',
                     control.disconnect,
                     enabled=control.is_connected),
                Separator,
                Item('&Read strengths', 'F9',
                     'Read magnet strengths from the online database',
                     control.on_read_all,
                     enabled=control.has_sequence),
                Item('Read &beam', None,
                     'Read beam settings from the online database',
                     control.on_read_beam,
                     enabled=control.has_sequence),
                Separator,
                Item('&Write strengths', None,
                     'Write magnet strengths to the online database',
                     control.on_write_all,
                     enabled=control.has_sequence),
                Separator,
                Item('Beam &diagnostic', None,
                     'Beam position and emittance diagnostics',
                     control.monitor_widget.create,
                     enabled=control.has_sequence),
                Separator,
                Item('ORM measurement', None,
                     'Measure ORM for later analysis',
                     control.orm_measure_widget.create,
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
                    Item('Measured &Response', 'Ctrl+R',
                         'Perform orbit correction empirically by measuring'
                         ' the orbit response.',
                         control.on_correct_measured_response_method,
                         enabled=control.has_sequence),
                ]),
                Separator,
                menu.Menu('&Settings', []),
            ]),
            Menu('&Help', [
                Item('About &madgui', None,
                     'About the madgui GUI application.',
                     self.helpAboutMadGUI.create),
                Item('About &cpymad', None,
                     'About the cpymad python binding to MAD-X.',
                     self.helpAboutCPyMAD.create),
                Item('About MAD-&X', None,
                     'About the included MAD-X backend.',
                     self.helpAboutMadX.create),
                Separator,
                Item('About &Python', None,
                     'About the currently running python interpreter.',
                     self.helpAboutPython.create),
                Item('About Q&t', None,
                     'About Qt.',
                     self.helpAboutQt),
            ]),
        ])
        self.acs_menu = items[-2]
        self.dc_action = self.acs_menu.actions()[0]
        self.acs_settings_menu = self.acs_menu.children()[-1]
        self.acs_settings_menu.setEnabled(False)

    dataReceived = Signal(object)

    def createControls(self):
        self.logWidget.highlight('SEND',     QColor(Qt.yellow).lighter(160))
        self.logWidget.highlight('MADX',     QColor(Qt.lightGray))

        self.logWidget.highlight('DEBUG',    QColor(Qt.blue).lighter(180))
        self.logWidget.highlight('INFO',     QColor(Qt.green).lighter(150))
        self.logWidget.highlight('WARNING',  QColor(Qt.yellow))
        self.logWidget.highlight('ERROR',    QColor(Qt.red))
        self.logWidget.highlight('CRITICAL', QColor(Qt.red))

        log_conf = self.config.logging
        self.logWidget.setup_logging('DEBUG')
        self.logWidget.maxlen = log_conf.maxlen
        self.logWidget.infobar.enable_timestamps(log_conf.times.enable)
        self.logWidget.infobar.set_timeformat(log_conf.times.format)
        self.logWidget.enable_logging(log_conf.enable)
        self.logWidget.set_loglevel(log_conf.level)
        self.logWidget.enable('SEND', log_conf.madx['in'])
        self.logWidget.enable('MADX', log_conf.madx['out'])

        self.dataReceived.connect(partial(
            self.logWidget.append_from_binary_stream, 'MADX'))

        self.timeCheckBox.setChecked(self.logWidget.infobar.show_time)
        self.loggingCheckBox.setChecked(self.logWidget.logging_enabled)
        self.loglevelComboBox.setEnabled(self.logWidget.logging_enabled)
        self.loglevelComboBox.setCurrentText(self.logWidget.loglevel)
        self.madxInputCheckBox.setChecked(self.logWidget.enabled('SEND'))
        self.madxOutputCheckBox.setChecked(self.logWidget.enabled('MADX'))

        self.timeCheckBox.clicked.connect(
            self.logWidget.infobar.enable_timestamps)
        self.loggingCheckBox.clicked.connect(
            self.logWidget.enable_logging)
        self.loglevelComboBox.currentTextChanged.connect(
            self.logWidget.set_loglevel)
        self.madxInputCheckBox.clicked.connect(
            partial(self.logWidget.enable, 'SEND'))
        self.madxOutputCheckBox.clicked.connect(
            partial(self.logWidget.enable, 'MADX'))

        style = self.style()
        self.undo_stack = undo_stack = UndoStack()
        self.undo_action = undo_stack.create_undo_action(self)
        self.redo_action = undo_stack.create_redo_action(self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.undo_action.setIcon(style.standardIcon(QStyle.SP_ArrowBack))
        self.redo_action.setIcon(style.standardIcon(QStyle.SP_ArrowForward))
        self.toolbar.addAction(self.undo_action)
        self.toolbar.addAction(self.redo_action)

    def log_command(self, text):
        text = text.rstrip()
        self.logWidget.append(LogRecord(
            time.time(), 'SEND', text))

    # Menu actions

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
            self.session.load_model(filename)

    def execFile(self):
        from madgui.widget.filedialog import getOpenFileName
        filters = [
            ("All MAD-X files", "*.madx", "*.str", "*.seq"),
            ("Strength files", "*.str"),
            ("All files", "*"),
        ]
        folder = self.exec_folder or self.folder
        filename = getOpenFileName(
            self, 'Open MAD-X file', folder, filters)
        if filename:
            self.model().call(filename)
            self.exec_folder = os.path.dirname(filename)

    def loadStrengths(self):
        self._import("Import magnet strengths", [
            ("YAML files", "*.yml", "*.yaml"),
            ("Strength files", "*.str"),
            ("All MAD-X files", "*.madx", "*.str", "*.seq"),
            ("All files", "*"),
        ], self.model().update_globals, data_key='globals')

    def loadBeam(self):
        self._import("Import beam parameters", [
            ("YAML files", "*.yml", "*.yaml"),
            ("All files", "*"),
        ], self.model().update_beam, data_key='beam')

    def loadTwiss(self):
        self._import("Import initial twiss parameters", [
            ("YAML files", "*.yml", "*.yaml"),
            ("All files", "*"),
        ], self.model().update_twiss_args, data_key='twiss')

    def _import(self, title, filters, callback, data_key):
        from madgui.widget.filedialog import getOpenFileName
        folder = self.str_folder or self.folder
        filename = getOpenFileName(self, title, folder, filters)
        if filename:
            from madgui.widget.params import import_params
            data = import_params(filename)
            callback(data)
            self.str_folder = os.path.dirname(filename)

    def saveStrengths(self):
        self._export("Save MAD-X strengths file", [
            ("YAML files", "*.yml", "*.yaml"),
            ("Strength files", "*.str"),
            ("All files", "*"),
        ], self.model().export_globals, data_key='globals')

    def saveBeam(self):
        # TODO: import/export MAD-X file (with only BEAM command)
        self._export("Export initial BEAM settings", [
            ("YAML files", "*.yml", "*.yaml"),
            ("All files", "*"),
        ], self.model().export_beam, data_key='beam')

    def saveTwiss(self):
        # TODO: import/export MAD-X file (with only TWISS command)
        self._export("Export initial TWISS settings", [
            ("YAML files", "*.yml", "*.yaml"),
            ("All files", "*"),
        ], self.model().export_twiss, data_key='twiss')

    def saveCommands(self):
        def write_file(filename, content):
            with open(filename, 'wt') as f:
                f.write(content)
        # TODO: save timestamps and chdirs as comments!
        # TODO: add generic `saveLog` command instead?
        self._export("Save MAD-X command session", [
            ("MAD-X files", "*.madx"),
            ("All files", "*"),
        ], lambda: "\n".join(self.model().madx.history), write_file)

    def _export(self, title, filters, fetch_data, export=None, **kw):
        from madgui.widget.filedialog import getSaveFileName
        folder = self.str_folder or self.folder
        filename = getSaveFileName(self, title, folder, filters)
        if filename:
            if export is None:
                from madgui.widget.params import export_params as export
            data = fetch_data()
            export(filename, data, **kw)
            self.str_folder = os.path.dirname(filename)

    def reverseSequence(self):
        """Reverse sequence from back to front. Experimental feature. Not
        implemented for all element types."""
        self.model().reverse()
        self.model().invalidate()

    @SingleWindow.factory
    def editInitialConditions(self):
        from madgui.widget.params import model_params_dialog
        return model_params_dialog(
            self.model(), parent=self, folder=self.folder)

    def viewShell(self):
        return self._createShell()

    def viewFloorPlan(self):
        from madgui.widget.floor_plan import FloorPlanWidget
        return Dialog(self, FloorPlanWidget(self.session))

    @SingleWindow.factory
    def viewMatchDialog(self):
        from madgui.widget.match import MatchWidget
        widget = MatchWidget(self.session.matcher)
        return Dialog(self, widget)

    def setLogSize(self):
        text = "Maximum log size (0 for infinite):"
        number, ok = QInputDialog.getInt(
            self, "Set log size", text,
            value=self.logWidget.maxlen, min=0)
        if ok:
            self.logWidget.maxlen = number

    def setInterpolate(self):
        text = "Number of points (0 to disable):"
        number, ok = QInputDialog.getInt(
            self, "Set number of data points", text,
            value=self.config.interpolate, min=0)
        if ok:
            self.config.interpolate = number

    def refreshTwiss(self):
        """Redo twiss and redraw plot."""
        self.model().invalidate()

    def setNumberFormat(self):
        fmtspec, ok = QInputDialog.getText(
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

    def toggleSpinBox(self):
        # TODO: sync with menu state
        self.config.number.spinbox = not self.config.number.spinbox

    def increaseFontSize(self):
        self.setFontSize(self.font().pointSize() + 1)

    def decreaseFontSize(self):
        self.setFontSize(self.font().pointSize() - 1)

    def setFontSize(self, size):
        delta = size - self.font().pointSize()
        if delta:
            for widget in QApplication.topLevelWidgets():
                size = widget.font().pointSize() + delta
                widget.setStyleSheet("font-size:{}pt;".format(max(size, 6)))

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

    @SingleWindow.factory
    def helpAboutPython(self):
        """Show about dialog."""
        import sys
        import site     # adds builtins.license/copyright/credits
        site            # silence pyflakes (suppress unused import warning)
        import builtins

        class About:
            __uri__ = "https::/www.python.org"
            __title__ = 'python'
            __version__ = ".".join(map(str, sys.version_info))
            __summary__ = sys.version + "\n\nPath: " + sys.executable
            __credits__ = str(builtins.credits)
            get_copyright_notice = lambda: sys.copyright
        return self._showAboutDialog(About)

    def helpAboutQt(self):
        QMessageBox.aboutQt(self)

    def _showAboutDialog(self, module):
        from madgui.widget.about import VersionInfo, AboutWidget
        info = VersionInfo(module)
        return Dialog(self, AboutWidget(info))

    # Update state

    def model_args(self, filename):
        return dict(
            command_log=self.log_command,
            stdout=self.dataReceived.emit,
            stderr=subprocess.STDOUT,
            undo_stack=self.undo_stack,
            interpolate=self.config.interpolate)

    def _on_model_changed(self, old_model, model):

        if old_model is not None:
            old_model.updated.disconnect(self.update_twiss)

        if model is None:
            self.user_ns.madx = None
            self.user_ns.twiss = None
            self.setWindowTitle("madgui")
            return

        model.updated.set_queued(True)

        self.session.folder = os.path.split(model.filename)[0]
        logging.info('Loading {}'.format(model.filename))

        self.user_ns.madx = model.madx
        self.user_ns.twiss = model.twiss()
        exec(model.data.get('onload', ''), self.user_ns.__dict__)

        model.updated.connect(self.update_twiss)

        from madgui.widget.elementinfo import InfoBoxGroup
        self.box_group = InfoBoxGroup(self, self.session.selected_elements)

        self.setWindowTitle(model.name)
        self.showTwiss()

    def update_twiss(self):
        self.user_ns.twiss = self.model().twiss()

    def showTwiss(self, name=None):
        from madgui.plot.twissfigure import TwissWidget
        widget = TwissWidget.from_session(self.session, name)
        scene = widget.scene
        self.views.append(scene)

        def destroyed():
            if scene in self.views:
                self.config.plot_windows.insert(
                    0, self._save_plot_window(scene))
                scene.destroy()
                self.views.remove(scene)

        notifyEvent(widget.window(), 'Close', destroyed)

    def _save_plot_window(self, scene):
        widget = scene.figure.canvas.window()
        return {
            'graph': scene.graph_name,
            'size': [widget.size().width(), widget.size().height()],
            'pos': [widget.pos().x(), widget.pos().y()],
        }

    def graphs(self, name):
        return [scene for scene in self.views if scene.graph_name == name]

    def open_graph(self, name):
        if name in self.graphs(name):
            return
        if self.views:
            self.views[-1].set_graph(name)
        else:
            self.showTwiss(name)
        return self.views[-1]

    def _createShell(self):
        """Create a python shell widget."""
        from madgui.widget.pyshell import PyShell
        return Dialog(self, PyShell(self.user_ns.__dict__))
