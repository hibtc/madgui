from contextlib import contextmanager

from PyQt5.QtWidgets import QUndoCommand, QUndoStack

from madgui.util.misc import invalidate


class UndoCommand(QUndoCommand):

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

    if not hasattr(QUndoCommand, 'setObsolete'):  # requires Qt 5.9
        def setObsolete(self, obsolete):
            pass


class UndoStack(QUndoStack):

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
            old = getattr(self.model, '_twiss', None)
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
                if old is None:
                    invalidate(self.model, 'twiss')
                else:
                    self.model._twiss = old
