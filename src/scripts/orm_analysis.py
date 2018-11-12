#! /usr/bin/env python3
"""
Utility for analyzing on ORM measurements.

Usage:
    ./orm_analysis.py MODEL RECORDS...

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
    OrbitResponse, plot_monitor_response,
    create_errors_from_spec, reduced_chisq)

from madgui.util.qt import monospace
from madgui.util.layout import VBoxLayout, HBoxLayout, Stretch
from madgui.plot.matplotlib import MultiFigure, PlotWidget as _PlotWidget

import madgui.util.yaml as yaml
import madgui.util.menu as menu


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

        self.setFont(monospace())

        self.confedit = QtGui.QPlainTextEdit()
        self.confedit.setPlainText(self.get_init_text())
        self.logwidget = QtGui.QPlainTextEdit()
        self.logwidget.setReadOnly(True)

        monitor_select = self.monitor_select = QtGui.QComboBox()
        monitor_select.addItems(measured.monitors)
        monitor_select.setCurrentText(measured.monitors[-1])
        monitor_select.currentTextChanged.connect(self.change_monitor)

        update_button = QtGui.QPushButton("Update")
        update_button.clicked.connect(lambda: self.update_model_orm(False))

        widget = QtGui.QWidget()
        widget.setLayout(HBoxLayout([
            self.confedit,
            self.logwidget,
            VBoxLayout([monitor_select, update_button, Stretch(1)]),
        ]))

        dock = QtGui.QDockWidget()
        dock.setWidget(widget)
        dock.setWindowTitle("Model errors")

        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.create_menu()
        self.figure = figure
        self.model_orm = None
        self.update_model_orm()

    def log(self, text, *args, **kwargs):
        self.logwidget.appendPlainText(text.format(*args, **kwargs))

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

    def update_model_orm(self, clear=True):
        errors = self.read_spec()
        with self.apply_errors(errors):
            measured = self.measured
            self.log("recalculating ORM…")
            self.model_orm = model_orm = self.model.get_orbit_response_matrix(
                measured.monitors, measured.knobs)
            stddev = measured.stddev
            self.log("red χ² = {}", reduced_chisq(
                (measured.orm - model_orm) / stddev, len(errors)))
            self.log("    |x = {}", reduced_chisq(
                ((measured.orm - model_orm) / stddev)[:, 0, :], len(errors)))
            self.log("    |y = {}", reduced_chisq(
                ((measured.orm - model_orm) / stddev)[:, 1, :], len(errors)))
        self.draw_figure(clear)

    def change_monitor(self, monitor):
        self.draw_figure()

    def draw_figure(self, clear=True):
        monitor = self.monitor_select.currentText()
        if clear:
            self.figure.backend_figure.clear()
            self.lines = plot_monitor_response(
                self.figure.backend_figure,
                monitor, self.model, self.measured, None, self.model_orm,
                "model versus measured ORM")
            self.figure.canvas.draw()
            self.figure.canvas.updateGeometry()
        else:
            i = self.measured.monitors.index(monitor)
            self.lines[0][0].set_ydata(self.model_orm[i, 0, :].flatten())
            self.lines[1][0].set_ydata(self.model_orm[i, 1, :].flatten())
            self.figure.canvas.draw()

    def read_spec(self):
        text = self.confedit.toPlainText()
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
{
# g3mu1->angle: 0.01,
# g3mu1->fint: 0.1,
# kl_g3qd11: 0.01,
# kl_g3qd12: 0.01,
# g3qd11<dx>: 0.001,
}
""".strip()


def main(args=None):
    opts = docopt(__doc__, args)
    app = init_app(['madgui'])

    model_file = opts['MODEL']
    record_files = opts['RECORDS']

    config = load_config(isolated=True)
    with Session(config) as session:
        session.load_model(
            model_file,
            stdout=False)
        model = session.model()
        measured = OrbitResponse.load(model, record_files)
        window = MainWindow(model, measured)
        window.show()
        return app.exec_()


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
