"""
Utility functions for use with QFileDialog.
"""

import os

from madqt.qt import QtGui


__all__ = [
    'make_filter',
]

def make_filter(wildcards):
    """
    Create wildcard string from multiple wildcard tuples.

    For example:

        >>> make_filter([
        ...     ('All files', '*'),
        ...     ('Text files', '*.txt', '*.log'),
        ... ])
        All files (*);;Text files (*.txt *.log)
    """
    return ';;'.join(make_filters(wildcards))


def make_filters(wildcards):
    return ["{0} ({1})".format(w[0], " ".join(w[1:]))
            for w in wildcards]


def _fileDialog(acceptMode, fileMode,
                parent=None, caption='', directory='', filters=(),
                selectedFilter=None, options=0):

    nameFilters = make_filters(filters)

    dialog = QtGui.QFileDialog(parent, caption, directory)
    dialog.setNameFilters(nameFilters)
    dialog.setAcceptMode(acceptMode)
    dialog.setFileMode(fileMode)
    dialog.setOptions(QtGui.QFileDialog.Options(options))
    if selectedFilter is not None:
        dialog.selectNameFilter(nameFilters[selectedFilter])

    if dialog.exec_() != QtGui.QDialog.Accepted:
        return None

    filename = dialog.selectedFiles()[0]
    selectedFilter = nameFilters.index(dialog.selectedNameFilter())

    _, ext = os.path.splitext(filename)

    if not ext:
        ext = filters[selectedFilter][1]    # use first extension
        if ext != '*' and ext != '*.*':
            return filename + ext[1:]       # remove leading '*'
    return filename



def getOpenFileName(*args, **kwargs):
    """
    Imitates ``QtGui.QFileDialog.getOpenFileName``, except that ``filter``
    is now ``filters`` that must be specified as a list.
    """
    return _fileDialog(QtGui.QFileDialog.AcceptOpen,
                       QtGui.QFileDialog.ExistingFile,
                       *args, **kwargs)


def getSaveFileName(*args, **kwargs):
    return _fileDialog(QtGui.QFileDialog.AcceptSave,
                       QtGui.QFileDialog.AnyFile,
                       *args, **kwargs)
