"""
Utilities to create widgets
"""

__all__ = [
    'Dialog',
]

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QSizePolicy

from madgui.util.layout import HBoxLayout, VBoxLayout, Stretch
from madgui.util.qt import present, notifyEvent

# short-hands:
Button = QDialogButtonBox


def perpendicular(orientation):
    """Get perpendicular orientation."""
    return (Qt.Horizontal | Qt.Vertical) ^ orientation


def expand(widget, orientation):
    """Expand widget in specified direction."""
    policy = widget.sizePolicy()
    if orientation == Qt.Horizontal:
        policy.setHorizontalPolicy(QSizePolicy.Minimum)
    else:
        policy.setVerticalPolicy(QSizePolicy.Minimum)
    widget.setSizePolicy(policy)


class SerializeButtons(QDialogButtonBox):

    """
    :ivar QWidget widget: the content area widget
    :ivar str folder: folder for exports/imports
    """

    def __init__(self, widget, folder, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.widget = widget
        self.folder = folder
        self.addButton(Button.Open).clicked.connect(self.onImport)
        self.addButton(Button.Save).clicked.connect(self.onExport)
        self.addButton(Button.Ok).clicked.connect(self.onAccept)
        self.button(Button.Open).setAutoDefault(False)
        self.button(Button.Save).setAutoDefault(False)
        self.button(Button.Ok).setDefault(True)
        expand(self, perpendicular(self.orientation()))

    def updateButtons(self):
        self.button(Button.Save).setEnabled(
            hasattr(self.exporter, 'exportTo'))
        self.button(Button.Open).setEnabled(
            hasattr(self.exporter, 'importFrom') and
            not getattr(self.exporter, 'readonly', None))

    @property
    def exporter(self):
        return getattr(self.widget, 'exporter', None)

    def onImport(self):
        """Import data from JSON/YAML file."""
        from madgui.widget.filedialog import getOpenFileName
        filename = getOpenFileName(
            self.window(), 'Import values', self.folder,
            self.exporter.importFilters)
        if filename:
            self.exporter.importFrom(filename)
            self.folder, _ = os.path.split(filename)

    def onExport(self):
        """Export data to YAML file."""
        from madgui.widget.filedialog import getSaveFileName
        filename = getSaveFileName(
            self.window(), 'Export values', self.folder,
            self.exporter.exportFilters)
        if filename:
            self.exporter.exportTo(filename)
            self.folder, _ = os.path.split(filename)

    def onAccept(self):
        self.window().accept()


class Dialog(QDialog):

    """
    Utility to wrap an application widget into a window with size-grip and
    optional buttons, and manage their lifetime via an owner.

    We distinguish between an `owner` and `parent` widget as follows:

    - dialogs always stay on top of the parent and share their taskbar entry
    - dialogs do not stay on top of the owner, nor share their taskbar entry,
      However: they will be kept alive as long as the owner, and when the
      owner is closed, will be closed as well.

    The second option is preferrable for most non-modal windows!

    - we want to allow the mainwindow in the foreground when focussed
    - we want to allow choosing between all windows from the taskbar
    """

    # TODO: reset button

    def __init__(self, owner=None, widget=None, *, parent=None, tight=True):
        super().__init__(parent)
        self.setSizeGripEnabled(True)
        self.finished.connect(self.close)
        self.event_filter = owner and notifyEvent(owner, 'Close', self.close)
        if widget is not None:
            self.setWidget(widget, VBoxLayout([widget], tight=tight))
            self.show()

    def setWidget(self, widget, layout):
        if widget.windowTitle():
            self.setWindowTitle(widget.windowTitle())
        self._widget = widget
        self.setLayout(layout)

    def widget(self):
        return self._widget

    # TODO: update enabled-state of apply-button?

    def closeEvent(self, event):
        # Prevent errors when closing the parent after the child:
        if self.event_filter:
            self.event_filter.uninstall()
        # send closeEvent to children!
        if hasattr(self.widget(), 'closeEvent'):
            self.widget().closeEvent(event)
        super().closeEvent(event)

    def setExportWidget(self, widget, folder):
        self.serious = SerializeButtons(widget, folder, Qt.Vertical)
        self.serious.addButton(Button.Cancel).clicked.connect(self.reject)
        self.setWidget(widget, HBoxLayout([widget, [
            Stretch(),
            self.serious,
        ]]))

    def setSimpleExportWidget(self, widget, folder):
        self.serious = SerializeButtons(widget, folder, Qt.Horizontal)
        self.setWidget(widget, VBoxLayout([
            widget,
            self.serious,
        ]))

    present = present
