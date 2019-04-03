"""
Utility for managing a simple history.
"""

__all__ = [
    'History',
]


from madgui.util.signal import Signal


class History:

    """
    Simple class for tracking a value through a linear change history.

    This is basically a list with the additional notion of a ``current
    revision`` which can be incremented or decremented by "undoing" or
    "redoing".
    """

    changed = Signal()

    def __init__(self):
        self.clear()

    def clear(self):
        """Clear history."""
        self._stack = []        # recorded revisions
        self._index = -1        # index of "current" value
        self.changed.emit()

    def push(self, value):
        """Add a value at our history position and clear anything behind.
        Keeps the value unique in the stack by removing previous appearance of
        it in the stack."""
        # check is so that we don't delete the history only by going back and
        # repushing the same value:
        if self() != value:
            self._index += 1
            del self._stack[self._index:]
            self._remove(value)
            self._stack.append(value)
            self.changed.emit()
        return value

    def undo(self):
        """Move backward in history."""
        if self.can_undo():
            self._index -= 1
            self.changed.emit()
            return True

    def redo(self):
        """Move forward in history."""
        if self.can_redo():
            self._index += 1
            self.changed.emit()
            return True

    def can_undo(self):
        """Check whether we can move backward in history."""
        return self._index > 0

    def can_redo(self):
        """Check whether we can move forward in history."""
        return self._index < len(self._stack) - 1

    def __call__(self):
        """Get the value at our current history position."""
        return self._stack[self._index] if self._index >= 0 else None

    def __len__(self):
        """Total number of items in the history."""
        return len(self._stack)

    def _remove(self, value):
        """Remove ``value`` from history."""
        try:
            index = self._stack.index(value)
        except ValueError:
            return
        del self._stack[index]
        if self._index > index:
            self._index -= 1

    def create_undo_action(self, parent):
        """Create a :class:`~PyQt5.QtWidgets.QAction` for an "Undo" button."""
        from PyQt5.QtWidgets import QAction, QStyle
        from PyQt5.QtGui import QKeySequence
        icon = parent.style().standardIcon(QStyle.SP_ArrowBack)
        action = QAction(icon, "Undo", parent)
        action.setShortcut(QKeySequence.Undo)
        action.setStatusTip("Undo")
        action.triggered.connect(self.undo)
        action.setEnabled(self.can_undo())
        self.changed.connect(lambda: action.setEnabled(self.can_undo()))
        return action

    def create_redo_action(self, parent):
        """Create a :class:`~PyQt5.QtWidgets.QAction` for a "Redo" button."""
        from PyQt5.QtWidgets import QAction, QStyle
        from PyQt5.QtGui import QKeySequence
        icon = parent.style().standardIcon(QStyle.SP_ArrowForward)
        action = QAction(icon, "Redo", parent)
        action.setShortcut(QKeySequence.Redo)
        action.setStatusTip("Redo")
        action.triggered.connect(self.redo)
        action.setEnabled(self.can_redo())
        self.changed.connect(lambda: action.setEnabled(self.can_redo()))
        return action
