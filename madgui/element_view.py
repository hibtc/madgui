"""
Popup view component for displaying info for individual line elements.
"""
import wx

class AutoSizedTextCtrl(wx.TextCtrl):
    def SetValue(self, value):
        value = str(value)
        minwidth = self.GetCharWidth() * len(value) * 1.2
        self.SetMinSize(wx.Size(int(minwidth), -1)) 
        return super(AutoSizedTextCtrl, self).SetValue(value)

class MadElementPopup(wx.Dialog):
    """
    View for a single element
    """
    def __init__(self, parent):
        super(MadElementPopup, self).__init__(
                parent=parent,
                style=wx.DEFAULT_DIALOG_STYLE|wx.SIMPLE_BORDER)

        self.grid = wx.FlexGridSizer(rows=0, cols=2, vgap=5, hgap=5)
        self.grid.SetFlexibleDirection(wx.HORIZONTAL)
        self.grid.AddGrowableCol(1, 1)
        self.grid.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_ALL)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.grid, flag=wx.ALL|wx.EXPAND, border=5)

        self.SetSizer(outer)
        self.Centre()

    @property
    def rows(self):
        """Access the displayed rows."""
        grid = self.grid
        num_rows = grid.CalcRowsCols()[0]
        for row in range(num_rows):
            if grid.GetItem(2*row):
                static = grid.GetItem(2*row).Window
                edit = grid.GetItem(2*row+1).Window
                yield static.LabelText, edit.Value

    @rows.setter
    def rows(self, rows):
        """Access the displayed rows."""
        grid = self.grid
        num_rows = grid.CalcRowsCols()[0]
        if len(rows) == num_rows:
            for row, (key, val) in enumerate(rows):
                grid.GetItem(2*row+0).Window.Value = key 
                grid.GetItem(2*row+1).Window.Value = val 
        else:
            grid.Clear()
            for key, val in rows:
                style = wx.TE_READONLY|wx.TE_RIGHT|wx.NO_BORDER
                label = wx.StaticText(self, label=key)
                text = AutoSizedTextCtrl(self, style=style)
                text.SetValue(val)
                grid.Add(label, flag=wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL)
                grid.Add(text, flag=wx.EXPAND|wx.ALIGN_CENTER_VERTICAL)

        self.Fit()


class MadElementView:
    """
    This controls MadElementPopup element view.
    """
    def __init__(self, popup, model, element_name):
        self.model = model
        self.element_name = element_name
        self.popup = popup
        self.update()
        model.update += lambda _: self.update()

    def update(self):
        el = self.model.element_by_name(self.element_name)
        rows = el.items()

        # convert to title case:
        rows = [(k.title(),v) for (k,v) in rows]

        # substitute nicer names:
        substitute = {'L': 'Length',
                      'At': 'Position'}
        rows = [(substitute.get(k,k),v) for (k,v) in rows]

        # presort alphanumerically:
        # (with some luck the order on the elements with equal key in the
        # subsequent sort will be left invariant)
        rows = sorted(rows)

        # sort preferred elements to top:
        order = ['Type',
                 'Name',
                 'Position',
                 'Length']
        order = dict(zip(order, range(-len(order), 0)))
        rows = sorted(rows, key=lambda row: order.get(row[0], len(order)))

        # add colon
        rows = [(k+':',v) for (k,v) in rows]

        # update view:
        self.popup.rows = rows

