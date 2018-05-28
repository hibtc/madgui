from collections import Mapping

from madgui.qt import QtGui


def items(d):
    return d.items() if isinstance(d, Mapping) else d

def trim(s):
    return s.replace(' ', '') if isinstance(s, str) else s


class UpdateCommand(QtGui.QUndoCommand):

    def __init__(self, old, new, write, text):
        super().__init__()
        old = {k.lower(): v for k, v in items(old)}
        new = {k.lower(): v for k, v in items(new)}
        # NOTE: This trims not only expressions (as intended) but also regular
        # string arguments (which is incorrect). However, this should be a
        # sufficiently rare use case, so we don't care for now…
        self._new = {k: v for k, v in items(new) if trim(old.get(k)) != trim(v)}
        self._old = {k: v for k, v in items(old) if k in self._new}
        self._old.update({k: None for k in self._new.keys() - self._old.keys()})
        self._set = write
        self.setText(text.format(", ".join(self._new)))

    def undo(self):
        self._set(self._old)

    def redo(self):
        self._set(self._new)

    def __bool__(self):
        return bool(self._new)
