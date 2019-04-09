"""
Open an ipython shell in a widget
"""

__all__ = [
    'PyShell',
]

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from pyqtconsole.console import PythonConsole


class PyShell(PythonConsole):

    """Create an in-process kernel."""

    def __init__(self, context, parent=None):
        super().__init__(parent, context)
        self.stdin.write_event.connect(
            self.repl_nonblock, Qt.ConnectionType.QueuedConnection)
        self.ctrl_d_exits_console(True)

    def _close(self):
        self.interpreter.exit()
        self.window().close()


if __name__ == "__main__":
    app = QApplication([])
    widget = PyShell({})
    widget.show()
    app.exec_()
