"""
Controller component for the MadGUI application.
"""

# wxpython
import wx
from element_view import MadElementPopup, MadElementView


class MadCtrl:
    """
    Controller class for a ViewPanel and MadModel
    """

    def __init__(self, model, panel):
        """Initialize observer and Subscribe as observer for user events."""
        self.cid_match = None
        self.cid_select = None
        self.model = model
        self.panel = panel
        self.view = panel.view

        def toggle_match(panel, event):
            if event.IsChecked():
                self.start_match()
            else:
                self.start_select()
        panel.OnMatchClick += toggle_match
        self.start_select()

    def start_select(self):
        """Start select mode."""
        self.stop_match()
        self.cid_select = self.view.figure.canvas.mpl_connect(
                'button_press_event',
                self.on_select)

    def stop_select(self):
        """Stop select mode."""
        if self.cid_select is not None:
            self.view.figure.canvas.mpl_disconnect(self.cid_select)
            self.cid_select = None

    def start_match(self):
        """Start matching mode."""
        self.stop_select()
        self.cid_match = self.view.figure.canvas.mpl_connect(
                'button_press_event',
                self.on_match)
        self.constraints = []

    def stop_match(self):
        """Stop matching mode."""
        if self.cid_match is not None:
            self.view.figure.canvas.mpl_disconnect(self.cid_match)
            self.cid_match = None
        self.model.clear_constraints()

    @property
    def frame(self):
        wnd = self.panel
        while wnd.GetParent():
            wnd = wnd.GetParent()
        return wnd

    def on_select(self, event):
        """Display a popup window with info about the selected element."""
        elem = self.model.element_by_position_center(event.xdata)
        if elem is None or 'name' not in elem:
            return
        popup = MadElementPopup(self.frame)
        element_view = MadElementView(popup, self.model, elem['name'])
        popup.Show()


    def on_match(self, event):
        elem = self.model.element_by_position_center(event.xdata)
        if elem is None or 'name' not in elem:
            return

        if self.view.curve[1]['factor'] < 0:
            if event.button == 1:
                axis = event.ydata < 0
            elif event.button == 2:
                self.model.remove_constraint(elem)
                return
            else:
                return
        else:
            if event.button == 1: # left mouse
                axis = 0
            elif event.button == 3: # right mouse
                axis = 1
            elif event.button == 2:
                self.model.remove_constraint(elem)
                return
            else:
                return

        orig_cursor = self.panel.GetCursor()
        wait_cursor = wx.StockCursor(wx.CURSOR_WAIT)
        self.panel.SetCursor(wait_cursor)

        # add the clicked constraint
        envelope = event.ydata*self.view.unit['y']['scale']*self.view.curve[axis]['factor']
        self.model.add_constraint(axis, elem, envelope)

        # add another constraint to hold the orthogonal axis constant
        orth_axis = 1-axis
        orth_env = self.model.get_envelope_center(elem, orth_axis)
        self.model.add_constraint(orth_axis, elem, orth_env)

        self.model.match()
        self.panel.SetCursor(orig_cursor)

