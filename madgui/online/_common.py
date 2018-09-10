
from madgui.qt import QtCore, QtGui
from madgui.util.qt import monospace
from madgui.util.layout import VBoxLayout, HBoxLayout
from madgui.widget.edit import LineNumberBar


class EditConfigDialog(QtGui.QDialog):

    def __init__(self, model, apply_callback):
        super().__init__()
        self.model = model
        self.apply_callback = apply_callback
        self.textbox = QtGui.QPlainTextEdit()
        self.textbox.setFont(monospace())
        self.linenos = LineNumberBar(self.textbox)
        buttons = QtGui.QDialogButtonBox()
        buttons.addButton(buttons.Ok).clicked.connect(self.accept)
        self.setLayout(VBoxLayout([
            HBoxLayout([self.linenos, self.textbox], tight=True),
            buttons,
        ]))
        self.setSizeGripEnabled(True)
        self.resize(QtCore.QSize(600, 400))
        self.setWindowTitle(self.model.filename)

        with open(model.filename) as f:
            text = f.read()
        self.textbox.appendPlainText(text)

    def accept(self):
        if self.apply():
            super().accept()

    def apply(self):
        text = self.textbox.toPlainText()
        return self.apply_callback(text)
