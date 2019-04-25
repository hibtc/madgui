import yaml

from PyQt5.QtCore import pyqtSlot as slot
from PyQt5.QtWidgets import QWidget, QMessageBox

from madgui.util.qt import load_ui
from madgui.widget.edit import TextEditDialog


class ConfigSelect(QWidget):

    """Widget that lets the user select config and x/y mode."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        load_ui(self, __package__, 'configselect.ui')

    def set_corrector(self, corrector, data_key):
        self.data_key = data_key
        self.corrector = corrector
        self.configs = corrector.model.data.get(self.data_key, {})
        self.active = next(iter(self.configs))
        self.corrector.setup(self.configs[self.active])
        self.update_config_items()
        self.modeXYButton.setChecked(True)

    def setEnabled(self, enabled):
        self.modeXButton.setEnabled(enabled)
        self.modeYButton.setEnabled(enabled)
        self.modeXYButton.setEnabled(enabled)
        self.editConfigButton.setEnabled(enabled)
        self.configComboBox.setEnabled(enabled)

    # Event handlers

    @slot()
    def on_modeXButton_clicked(self):
        self.set_xy_mode('x')

    @slot()
    def on_modeYButton_clicked(self):
        self.set_xy_mode('y')

    @slot()
    def on_modeXYButton_clicked(self):
        self.set_xy_mode('xy')

    @slot(int)
    def on_configComboBox_currentIndexChanged(self, index):
        name = self.configComboBox.itemText(index)
        self.corrector.setup(self.configs[name], self.corrector.mode)

    @slot()
    def on_editConfigButton_clicked(self):
        model = self.corrector.model
        with open(model.filename) as f:
            text = f.read()
        dialog = TextEditDialog(text, self.apply_config)
        dialog.setWindowTitle(model.filename)
        dialog.exec_()

    # internal

    def update_config_items(self):
        self.configComboBox.clear()
        self.configComboBox.addItems(list(self.configs))
        self.configComboBox.setCurrentText(self.active)

    def set_xy_mode(self, dirs):
        """Set corrector to perform only in x or y plane or both."""
        self.corrector.setup(self.configs[self.active], dirs)

    def apply_config(self, text):
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            QMessageBox.critical(
                self,
                'Syntax error in YAML document',
                'There is a syntax error in the YAML document, please edit.')
            return False

        configs = data.get(self.data_key)
        if not configs:
            QMessageBox.critical(
                self,
                'No config defined',
                'No configuration for this method defined.')
            return False

        model = self.corrector.model
        with open(model.filename, 'w') as f:
            f.write(text)

        self.configs = configs
        model.data[self.data_key] = configs
        conf = configs.get(self.active, next(iter(configs)))

        self.corrector.setup(conf)
        self.update_config_items()

        return True
