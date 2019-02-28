"""
Utilities for the optic variation method (Optikvarianzmethode) for beam
alignment.
"""

__all__ = [
    'CorrectorWidget',
]

from .multi_grid import CorrectorWidget as _Widget


class CorrectorWidget(_Widget):

    ui_file = 'optic_variation.ui'
    data_key = 'optic_variation'
    multi_step = True

    def init_controls(self):
        self.opticsTable.set_corrector(self.corrector)
        self.recordsTable.set_corrector(self.corrector)
        self.manProcWidget.set_corrector(self.corrector)
        self.autoProcWidget.set_corrector(self.corrector)
        super().init_controls()

    def set_initial_values(self):
        self.opticsTable.read_focus()
        self.update_status()

    def update_ui(self):
        super().update_ui()
        running = self.autoProcWidget.bot.running
        has_fit = bool(self.corrector.saved_optics())
        self.applyButton.setEnabled(not running and has_fit)
        self.configSelect.setEnabled(not running)
        self.manTab.setEnabled(not running)
        self.opticsTable.setEnabled(not running)
        self.recordsTable.setEnabled(not running)
