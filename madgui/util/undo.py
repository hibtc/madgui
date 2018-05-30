from contextlib import contextmanager

from madgui.qt import QtGui


class UndoCommand(QtGui.QUndoCommand):

    def __init__(self, old, new, write, text):
        super().__init__()
        self._old = new
        self._new = old
        self._set = write
        self.setText(text)

    def undo(self):
        self._set(self._old)

    def redo(self):
        self._set(self._new)


class UndoStack(QtGui.QUndoStack):

    @contextmanager
    def macro(self, text):
        self.beginMacro(text)
        try:
            yield None
        finally:
            self.endMacro()
            macro = self.command(self.count()-1)
            if macro.childCount() == 0:
                macro.setObsolete(True)
                self.undo()

    @contextmanager
    def rollback(self, text="temporary change", hidden=False):
        self.beginMacro(text)
        try:
            yield None
        finally:
            self.endMacro()
            macro = self.command(self.count()-1)
            if macro.childCount() == 0 or hidden:
                macro.setObsolete(True)
            self.undo()
