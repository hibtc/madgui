"""
Open an ipython shell in a widget
"""

__all__ = [
    'PyShell',
]

from PyQt5.QtWidgets import QApplication
from pyqtconsole.console import PythonConsole


class PyShell(PythonConsole):

    """Create an in-process kernel."""

    def __init__(self, context, parent=None):
        super().__init__(parent, context)
        self.ctrl_d_exits_console(True)
        self.eval_queued()

    def _close(self):
        # prevent feedback loop:
        if self.window().isVisible():
            self.window().close()


if __name__ == "__main__":
    app = QApplication([])
    widget = PyShell({})
    widget.show()
    app.exec_()
