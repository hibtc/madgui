"""
Popup view component for displaying info for individual line elements.
"""
import wx

class MadElementPopup(wx.PopupDialog):
    """
    View for a single element
    """
    def __init__(self, event):
        sizer = wx.FlexGridSizer(rows=4, cols=2)
        sizer.SetFlexibleDirection(wx.HORIZONTAL)
        sizer.AddGrowableCol(1, 1)
        sizer.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_ALL)
        self.SetSizer(sizer)

    @property
    def rows(self):
        """Access the displayed rows."""
        sizer = self.GetSizer()
        for row in range(self.Rows):
            static = sizer.GetItem(2*row).Window
            edit = sizer.GetItem(2*row+1).Window
            yield static.LabelText, edit.Value

    @rows.set
    def rows(self, rows):
        """Access the displayed rows."""
        known = {k:i for i,(k,v) in zip(range(self.Rows), self.rows)}
        added = {}
        sizer = self.GetSizer()
        # Add/update fields
        for key, val in rows:
            if key in known:
                sizer.GetItem(2*row+1).Window.Value = val 
            else:
                sizer.Add(wx.StaticText(self, label=key))
                sizer.Add(wx.TextCtrl(self, value=val))
            added[key] = True
        # Remove obsolete fields:
        for key in added:
            del known[key]
        for key in sorted(known, key=lambda k: known[k], reverse=True):
            sizer.Remove(2*known[key]+1)
            sizer.Remove(2*known[key])
        sizer.Layout()


class MadElementView:
    """
    This controls MadElementPopup element view.
    """
    def __init__(self, popup, model, element_name):
        self.model = model
        self.element_name = element_name
        self.popup = popup

    def update(self):
        el = self.model.element_by_name(self.element_name)
        self.popup.rows = [el.items()]

