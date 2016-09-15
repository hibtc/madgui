# encoding: utf-8
"""
Utilities to create widgets
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from madqt.qt import Qt, QtCore, QtGui

from madqt.core.base import Object, Signal
from madqt.util.layout import HBoxLayout, VBoxLayout, Stretch, Spacing


__all__ = [
    'Exporter',
    'Dialog',
]


# short-hand for accessing QDialogButtonBox.StandardButtons identifiers:
Button = QtGui.QDialogButtonBox


def perpendicular(orientation):
    return (Qt.Horizontal|Qt.Vertical) ^ orientation


def expand(widget, orientation):
    policy = widget.sizePolicy()
    if orientation == Qt.Horizontal:
        policy.setHorizontalPolicy(QtGui.QSizePolicy.Minimum)
    else:
        policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
    widget.setSizePolicy(policy)



class SerializeButtons(QtGui.QDialogButtonBox):

    """
    :ivar QWidget widget: the content area widget
    :ivar str folder: folder for exports/imports
    """

    def __init__(self, widget, folder, *args, **kwargs):
        super(SerializeButtons, self).__init__(*args, **kwargs)
        self.widget = widget
        self.folder = folder
        self.addButton(Button.Open).clicked.connect(self.onImport)
        self.addButton(Button.Save).clicked.connect(self.onExport)
        expand(self, perpendicular(self.orientation()))

    def onImport(self):
        """Import data from JSON/YAML file."""
        filename = QtGui.QFileDialog.getOpenFileName(
            self.window(), 'Import values', self.folder,
            self.widget.exportFilters)
        if isinstance(filename, tuple):
            filename, selected_filter = filename
        if filename:
            self.widget.importFrom(filename)
            self.folder, _ = os.path.split(filename)

    def onExport(self):
        """Export data to YAML file."""
        filename = QtGui.QFileDialog.getSaveFileName(
            self.window(), 'Export values', self.folder,
            self.widget.importFilters)
        if isinstance(filename, tuple):
            filename, selected_filter = filename
        if filename:
            self.widget.exportTo(filename)
            self.folder, _ = os.path.split(filename)


class Dialog(QtGui.QDialog):

    applied = Signal()
    # TODO: reset button

    def __init__(self, *args, **kwargs):
        super(Dialog, self).__init__(*args, **kwargs)
        self.setSizeGripEnabled(True)
        self.accepted.connect(self.apply)

    def setWidget(self, widget):
        if isinstance(widget, list):
            layout = VBoxLayout(widget)
        elif isinstance(widget, QtGui.QLayout):
            layout = widget
        elif isinstance(widget, QtGui.QWidget):
            layout = VBoxLayout([widget])
            layout.setContentsMargins(0, 0, 0, 0)
        else:
            raise NotImplementedError
        self.setLayout(layout)

    def apply(self):
        self.applied.emit()

    # TODO: update enabled-state of apply-button?

    def standardButtons(self, *args, **kwargs):
        buttons = QtGui.QDialogButtonBox(*args, **kwargs)
        buttons.addButton(Button.Ok).clicked.connect(self.accept)
        buttons.addButton(Button.Apply).clicked.connect(self.apply)
        buttons.addButton(Button.Cancel).clicked.connect(self.reject)
        return buttons

    def setButtonWidget(self, widget):
        self.setWidget([widget, self.standardButtons()])

    def setExportWidget(self, widget, folder):
        self.setWidget(HBoxLayout([widget, [
            SerializeButtons(widget, folder, Qt.Vertical),
            Stretch(),
            Spacing(20),
            self.standardButtons(Qt.Vertical),
        ]]))
