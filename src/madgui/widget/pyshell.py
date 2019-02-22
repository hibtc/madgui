"""
Open an ipython shell in a widget
"""

from PyQt5.QtWidgets import QApplication
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.inprocess import QtInProcessKernelManager


def create(context):
    """Create an in-process kernel."""
    manager = QtInProcessKernelManager()
    manager.start_kernel(show_banner=False)
    kernel = manager.kernel
    kernel.gui = 'qt'
    kernel.user_ns = context

    client = manager.client()
    client.start_channels()

    widget = RichJupyterWidget()
    widget.kernel_manager = manager
    widget.kernel_client = client
    return widget


if __name__ == "__main__":
    app = QApplication([])
    widget = create({})
    widget.show()
    app.exec_()
