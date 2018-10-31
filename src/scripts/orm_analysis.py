#! /usr/bin/env python3
"""
Utility for analyzing on ORM measurements.

Usage:
    ./orm_analysis.py (-i | -s SPEC) MODEL RECORDS...

Options:
    -i, --interactive       Interactive mode
    -s SPEC, --spec SPEC    Fit specification file

Arguments:
    MODEL must be the path of the model/sequence file to initialize MAD-X.

    RECORDS is a list of record YAML files that were dumped by madgui's ORM
    dialog.
"""

from contextlib import contextmanager, ExitStack

from docopt import docopt

from madgui.qt import Qt, QtGui
from madgui.core.app import init_app
from madgui.core.session import Session
from madgui.core.config import load as load_config
from madgui.model.orm import (
    analyze, load_yaml, OrbitResponse, plot_monitor_response,
    create_errors_from_spec)

from madgui.util.qt import monospace
from madgui.util.layout import VBoxLayout, HBoxLayout
from madgui.plot.matplotlib import MultiFigure, PlotWidget as _PlotWidget

import madgui.util.yaml as yaml
import madgui.util.menu as menu


class ConfigEditor(QtGui.QWidget):

    def __init__(self, update):
        super().__init__()
        self.textbox = QtGui.QPlainTextEdit()
        self.textbox.setFont(monospace())
        self.update_button = QtGui.QPushButton("Update")
        buttons = VBoxLayout([
            self.update_button,
        ])
        buttons.addStretch()
        self.setLayout(VBoxLayout([
            HBoxLayout([self.textbox, buttons], tight=True),
        ]))
        self.update_button.clicked.connect(update)


class PlotWidget(_PlotWidget):

    def _mouse_event(self, signal, mpl_event):
        pass


class MainWindow(QtGui.QMainWindow):

    def __init__(self, model, measured):
        super().__init__()
        self.model = model
        self.measured = measured
        figure = MultiFigure()
        canvas = PlotWidget(figure)
        self.setCentralWidget(canvas)
        edit = ConfigEditor(self.update_model_orm)
        dock = QtGui.QDockWidget()
        dock.setWidget(edit)
        dock.setWindowTitle("Model errors")
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.create_menu()
        self.textbox = edit.textbox
        self.textbox.setPlainText(self.get_init_text())
        self.figure = figure
        self.model_orm = None
        self.update_model_orm()

    def create_menu(self):
        Menu, Item = menu.Menu, menu.Item
        menubar = self.menuBar()
        menu.extend(self, menubar, [
            Menu('&Window', [
                Item('&Quit', 'Ctrl+Q', 'Close window',
                     self.close, QtGui.QStyle.SP_DialogCloseButton)
            ]),
            Menu('&Model', [
                Item('&Update', 'F5', 'Update model ORM',
                     self.update_model_orm, QtGui.QStyle.SP_BrowserReload),
            ]),
        ])

    def update_model_orm(self):
        errors = self.read_spec()
        with self.apply_errors(errors):
            self.model_orm = self.model.get_orbit_response_matrix(
                self.measured.monitors, self.measured.knobs)
        self.draw_figure()

    def draw_figure(self):
        self.figure.backend_figure.clear()
        plot_monitor_response(
            self.figure.backend_figure,
            'g3dg3g', self.model, self.measured, self.model_orm,
            "model versus measured ORM")
        self.figure.canvas.draw()
        self.figure.canvas.updateGeometry()

    def read_spec(self):
        text = self.textbox.toPlainText()
        args = yaml.safe_load(text)
        return create_errors_from_spec(args)

    @contextmanager
    def apply_errors(self, errors):
        self.model.madx.use(self.model.seq_name)
        self.model.madx.eoption(add=True)
        with ExitStack() as stack:
            for error in errors:
                stack.enter_context(error.vary(self.model))
            yield None

    def get_init_text(self):
        return """
knobs: {}
ealign: {}
efcomp: []
""".strip()


def main(args=None):
    opts = docopt(__doc__, args)
    app = QtGui.QApplication([])
    init_app(app)

    model_file = opts['MODEL']
    record_files = opts['RECORDS']

    config = load_config(isolated=True)
    with Session(config) as session:
        session.load_model(
            model_file,
            stdout=False)
        model = session.model()
        measured = OrbitResponse.load(model, record_files)
        if opts['--interactive']:
            window = MainWindow(model, measured)
            window.show()
            return app.exec_()
        else:
            spec_file = opts['--spec']
            return analyze(
                model, measured,
                load_yaml(spec_file)['analysis'])


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
