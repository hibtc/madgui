"""
Controller component for the MadGUI application.
"""

# wxpython
import wx

class MadCtrl(object):
    """
    Controller class for a ViewPanel and MadModel
    """

    def __init__(self, model, panel):
        """Initialize observer and Subscribe as observer for user events."""
        self.cid = None
        self.model = model
        self.panel = panel
        self.view = panel.view

        def toggle_match(panel, event):
            if event.IsChecked():
                self.start_match()
            else:
                self.stop_match()
        panel.OnMatchClick += toggle_match

    def start_match(self):
        """Start matching mode."""
        self.cid = self.view.figure.canvas.mpl_connect(
                'button_press_event',
                self.on_match)
        self.constraints = []

    def on_match(self, event):
        axes = event.inaxes
        if axes is None:
            return
        axis = 0 if axes is self.view.axes.x else 1

        elem = self.model.element_by_position_center(event.xdata)
        if elem is None or 'name' not in elem:
            return

        if event.button == 2:
            self.model.remove_constraint(elem)
            return
        elif event.button != 1:
            return

        orig_cursor = self.panel.GetCursor()
        wait_cursor = wx.StockCursor(wx.CURSOR_WAIT)
        self.panel.SetCursor(wait_cursor)

        # add the clicked constraint
        envelope = event.ydata*self.view.unit.y['scale']
        self.model.add_constraint(axis, elem, envelope)

        # add another constraint to hold the orthogonal axis constant
        orth_axis = 1-axis
        orth_env = self.model.get_envelope_center(elem, orth_axis)
        self.model.add_constraint(orth_axis, elem, orth_env)

        self.model.match()
        self.panel.SetCursor(orig_cursor)

    def stop_match(self):
        """Stop matching mode."""
        self.view.figure.canvas.mpl_disconnect(self.cid)
        self.cid = None
        self.model.clear_constraints()

