"""
Utility functions for use with QFileDialog.
"""

__all__ = [
    'getOpenFileName',
    'getSaveFileName',
    'getSaveFolderName',
    'getFileName',
    'FileWidget',
]

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QFileDialog, QLineEdit

from madgui.util.signal import Signal


MODE_OPEN = 0
MODE_SAVE = 1


def make_filters(wildcards):
    """
    Create wildcard string from multiple wildcard tuples.

    For example:

        >>> make_filters([
        ...     ('All files', '*'),
        ...     ('Text files', '*.txt', '*.log'),
        ... ])
        ['All files (*)', 'Text files (*.txt *.log)']
    """
    return ["{0} ({1})".format(w[0], " ".join(w[1:]))
            for w in wildcards]


def _fileDialog(acceptMode, fileMode,
                parent=None, caption='', directory='', filters=(),
                selectedFilter=None, options=0):

    nameFilters = make_filters(filters)

    dialog = QFileDialog(parent, caption, directory)
    dialog.setNameFilters(nameFilters)
    dialog.setAcceptMode(acceptMode)
    dialog.setFileMode(fileMode)
    dialog.setOptions(QFileDialog.Options(options))
    if selectedFilter is not None:
        dialog.selectNameFilter(nameFilters[selectedFilter])

    if dialog.exec_() != QDialog.Accepted:
        return None

    filename = dialog.selectedFiles()[0]
    if fileMode != QFileDialog.Directory:
        selectedFilter = nameFilters.index(dialog.selectedNameFilter())

        _, ext = os.path.splitext(filename)

        if not ext:
            ext = filters[selectedFilter][1]    # use first extension
            if ext.startswith('*.') and ext != '*.*':
                return filename + ext[1:]       # remove leading '*'
    return filename


def getOpenFileName(*args, **kwargs):
    """
    Imitates ``QFileDialog.getOpenFileName``, except that ``filter``
    is now ``filters`` that must be specified as a list.
    """
    return _fileDialog(QFileDialog.AcceptOpen,
                       QFileDialog.ExistingFile,
                       *args, **kwargs)


def getSaveFileName(*args, **kwargs):
    return _fileDialog(QFileDialog.AcceptSave,
                       QFileDialog.AnyFile,
                       *args, **kwargs)


def getSaveFolderName(*args, **kwargs):
    return _fileDialog(QFileDialog.AcceptSave,
                       QFileDialog.Directory,
                       *args, options=QFileDialog.ShowDirsOnly,
                       **kwargs)


def getFileName(mode, *args, **kwargs):
    if mode == MODE_OPEN:
        return getOpenFileName(*args, **kwargs)
    else:
        return getSaveFileName(*args, **kwargs)


class FileWidget(QLineEdit):

    mode = MODE_OPEN
    title = 'Open file'
    filters = None
    filename = None
    folder = None

    file_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setPlaceholderText("filename")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Space):
            self.show_open_dialog()
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.show_open_dialog()
        super().mousePressEvent(event)

    def set_filename(self, filename):
        changed = filename != self.filename
        if filename is None:
            self.filename = None
            self.folder = None
            self.clear()
        else:
            self.filename = filename
            self.folder = os.path.dirname(os.path.abspath(filename))
            self.setText(filename)
        if changed:
            self.file_changed.emit(filename)

    def show_open_dialog(self):
        filename = getFileName(self.mode, self.title, self.folder, self.filters)
        if filename is not None:
            self.set_filename(filename)
