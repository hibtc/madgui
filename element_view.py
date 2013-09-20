"""
Popup view component for displaying info for individual line elements.
"""
import wx

class MadElementPopup(wx.PopupWindow):
    """
    View for a single element
    """
    def __init__(self, parent):
        super(MadElementPopup, self).__init__(parent, flags=wx.SIMPLE_BORDER)
        self.panel = wx.Panel(self)

        sizer = wx.FlexGridSizer(rows=4, cols=2)
        sizer.SetFlexibleDirection(wx.HORIZONTAL)
        sizer.AddGrowableCol(1, 1)
        sizer.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_ALL)
        self.panel.SetSizer(sizer)

        self.Centre()
        self.Layout()

    @property
    def rows(self):
        """Access the displayed rows."""
        sizer = self.panel.GetSizer()
        for row in range(sizer.Rows):
            if sizer.GetItem(2*row):
                static = sizer.GetItem(2*row).Window
                edit = sizer.GetItem(2*row+1).Window
                yield static.LabelText, edit.Value

    @rows.setter
    def rows(self, rows):
        """Access the displayed rows."""
        sizer = self.panel.GetSizer()
        known = {k:i for i,(k,v) in zip(range(sizer.Rows), self.rows)}
        added = {}
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
            if key in known:
                del known[key]
        for key in sorted(known, key=lambda k: known[k], reverse=True):
            sizer.Remove(2*known[key]+1)
            sizer.Remove(2*known[key])
        sizer.Fit(self)
        self.Layout()


class MadElementView:
    """
    This controls MadElementPopup element view.
    """
    def __init__(self, popup, model, element_name):
        self.model = model
        self.element_name = element_name
        self.popup = popup
        self.update()

    def update(self):
        el = self.model.element_by_name(self.element_name)
        self.popup.rows = list(el.items())

