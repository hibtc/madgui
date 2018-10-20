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

    if not hasattr(QtGui.QUndoCommand, 'setObsolete'):  # requires Qt 5.9
        def setObsolete(self, obsolete):
            pass


class UndoStack(QtGui.QUndoStack):

    # FIXME: `macro` and `rollback` are not reentrant because `command(...)`
    # won't with nested macros. In order to fix this, we would need to
    # implement our own macro mechanism or add appropriate guards in these
    # methods.

    @contextmanager
    def macro(self, text):
        self.beginMacro(text)
        try:
            yield None
        finally:
            self.endMacro()
            macro = self.command(self.count()-1)
            if macro.childCount() == 0:
                try:
                    macro.setObsolete(True)
                except AttributeError:
                    pass
                self.undo()

    @contextmanager
    def rollback(self, text="temporary change", hidden=False, transient=False):
        if transient:
            invalid = self.model.twiss.invalid  # TODO: model member variable…
        self.beginMacro(text)
        try:
            yield None
        finally:
            self.endMacro()
            macro = self.command(self.count()-1)
            if macro.childCount() == 0 or hidden:
                try:
                    macro.setObsolete(True)
                except AttributeError:
                    pass
            self.undo()
            if transient:
                self.model.twiss.invalid = invalid
