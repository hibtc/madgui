"""
This module provides a lightweight alternative for the ``QUndoStack`` that
can be used in the absence of Qt and without initializing a ``QApplication``.
"""

__all__ = [
    'Command',
    'UndoCommand',
    'UndoStack',
]

from contextlib import contextmanager
import logging

from madgui.util.misc import invalidate
from madgui.util.signal import Signal


class Command:

    """Base class for un-/re-doable actions. Command objects are only to
    be pushed onto an UndoStack and must not be called directly."""

    text = ''

    def undo(self):
        """Undo the action represented by this command."""

    def redo(self):
        """Exec the action represented by this command."""


class UndoCommand(Command):

    """
    A diff-based state transition, initialized with ``old`` and ``new`` values
    that must be ``apply``-ed to go backward or forward in time.
    """

    def __init__(self, old, new, apply, text):
        self._old = new
        self._new = old
        self._apply = apply
        self.text = text

    def undo(self):
        """Go backward in time by applying the ``old`` state."""
        self._apply(self._old)

    def redo(self):
        """Go forward in time by applying the ``new`` state."""
        self._apply(self._new)


class Stack:

    # TODO: merge this class with History and Selection

    def __init__(self, items=None):
        self.items = [] if items is None else items
        self.index = 0

    def clear(self):
        """Empty the stack."""
        self.items.clear()
        self.index = 0

    def push(self, item):
        """Remove all items past our current position."""
        self.items[self.index:] = [item]
        self.index += 1

    def pop(self):
        """Read the previous value from the buffer."""
        if self.index > 0:
            self.index -= 1
            return self.items[self.index]

    def unpop(self):
        """Increase index by one and return the newly available item."""
        if self.index < len(self.items):
            self.index += 1
            return self.items[self.index - 1]

    def can_pop(self):
        """Check whether an item can be popped from the stack."""
        return self.index > 0

    def can_unpop(self):
        """Check whether an item is available past the top of the stack."""
        return self.index < len(self.items)

    def top(self):
        """Get the top item."""
        if self.index > 0:
            return self.items[self.index - 1]

    def truncate(self):
        """Forget all elements above current index."""
        del self.items[self.index:]


class Macro(Command):

    """An accumulation of multiple recorded subcommands."""

    def __init__(self, text, commands=None):
        self.text = text
        self.commands = [] if commands is None else commands

    def undo(self):
        """Undo all subcommands in reverse order."""
        for command in self.commands[::-1]:
            command.undo()

    def redo(self):
        """Exec all subcommands in original order."""
        for command in self.commands:
            command.redo()

    def count(self):
        """Return number of commands."""
        return len(self.commands)


class UndoStack:

    """
    Serves as lightweight replacement for QUndoStack.
    """

    changed = Signal()

    def __init__(self):
        self._root = Stack()
        self._leaf = self._root

    def clear(self):
        """Clear the stack. This can only be done when no macro is active."""
        assert self._leaf is self._root
        self._root.clear()
        self.changed.emit()

    def push(self, command):
        """Push and execute command, and truncate all history after current
        stack position."""
        self._leaf.push(command)
        command.redo()
        self.changed.emit()

    def truncate(self):
        """Truncate history after current stack position."""
        self._leaf.truncate()
        self.changed.emit()

    def count(self):
        """Return number of commands on the stack."""
        return len(self._root.items)

    def command(self, index):
        """Return the i-th command in the stack."""
        return self._root.items[index]

    def can_undo(self):
        """Check if an undo action can be performed."""
        return self._leaf.can_pop()

    def can_redo(self):
        """Check if a redo action can be performed."""
        return self._leaf.can_unpop()

    def undo(self):
        """Undo command before current stack pointer."""
        if self._leaf.can_pop():
            command = self._leaf.pop()
            command.undo()
            self.changed.emit()

    def redo(self):
        """Redo command behind current stack pointer."""
        if self._leaf.can_unpop():
            command = self._leaf.unpop()
            command.redo()
            self.changed.emit()

    @contextmanager
    def macro(self, text=""):
        if text:
            logging.info(text)
        stack = Stack()
        macro = Macro(text, stack.items)
        backup = self._leaf
        try:
            self.push(macro)    # These two lines must be in this order to
            self._leaf = stack  # avoid an infinite recursion!
            yield macro
        finally:
            self._leaf = backup
            stack.truncate()
            if macro.count() == 0 and self._leaf.top() is macro:
                self.undo()
                self.truncate()

    @contextmanager
    def rollback(self, text="temporary change", transient=False):
        macro = None
        if transient:
            old = getattr(self.model, '_twiss', None)
        try:
            with self.macro(text) as macro:
                yield macro
        finally:
            if self._leaf.top() is macro:
                self.undo()
                self.truncate()
            if transient:
                if old is None:
                    invalidate(self.model, 'twiss')
                else:
                    self.model._twiss = old

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
