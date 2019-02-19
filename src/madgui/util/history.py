"""
Utility for managing a simple history.
"""


class History:

    """
    Simple class for tracking a value through a linear change history.

    This is basically a list with the additional notion of a ``current
    revision`` which can be incremented or decremented by "undoing" or
    "redoing".
    """

    def __init__(self):
        self.clear()

    def clear(self):
        """Clear history."""
        self._stack = []        # recorded revisions
        self._index = -1        # index of "current" value

    def push(self, value):
        """Add a value at our history position and clear anything behind."""
        if self() != value:
            self._index += 1
            self._stack[self._index:] = [value]
        return value

    def undo(self):
        """Move backward in history."""
        if self.can_undo():
            self._index -= 1
            return True

    def redo(self):
        """Move forward in history."""
        if self.can_redo():
            self._index += 1
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
