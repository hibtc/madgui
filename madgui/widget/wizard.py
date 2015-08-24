"""
Module for wizard dialogs.
"""

import wx

from .input import Dialog


class WizardPage(wx.Panel):

    def __init__(self, parent, title):
        wx.Panel.__init__(self, parent)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)

        self.ctrl_title = wx.StaticText(self, label=title)
        self.ctrl_title.SetFont(wx.Font(18, wx.SWISS, wx.NORMAL, wx.BOLD))

        self.canvas = wx.Panel(self)

        self.sizer.Add(self.ctrl_title, 0, wx.ALIGN_CENTRE|wx.ALL, 5)
        self.sizer.Add(wx.StaticLine(self, -1), 0, wx.EXPAND|wx.ALL, 5)
        self.sizer.Add(self.canvas, 1, wx.EXPAND|wx.ALL, 5)


class Wizard(Dialog):

    def __init__(self, *args, **kwargs):
        self.pages = []
        self.cur_page = 0
        super(Wizard, self).__init__(*args, **kwargs)

    def CreateContentArea(self):
        """Create a sizer with the content area controls."""
        # Nesting a panel is necessary since automatic validation uses only
        # the validators of *child* windows.
        self.ContentArea = wx.Panel(self)
        self.content_sizer = wx.BoxSizer(wx.VERTICAL)
        self.ContentArea.SetSizer(self.content_sizer)
        return self.ContentArea

        # add prev/next buttons
    def CreateButtonArea(self):
        self.button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.prev_button = wx.Button(self, wx.ID_BACKWARD, label="&Back")
        self.next_button = wx.Button(self, wx.ID_FORWARD, label="&Forward")
        self.finish_button = wx.Button(self, wx.ID_APPLY, label="&Apply")
        self.cancel_button = wx.Button(self, wx.ID_CANCEL, label="&Cancel")

        self.prev_button.Bind(wx.EVT_BUTTON, self.OnPrevButton)
        self.next_button.Bind(wx.EVT_BUTTON, self.OnNextButton)
        self.finish_button.Bind(wx.EVT_BUTTON, self.OnFinishButton)

        self.prev_button.Bind(wx.EVT_UPDATE_UI, self.UpdatePrevButton)
        self.next_button.Bind(wx.EVT_UPDATE_UI, self.UpdateNextButton)
        self.finish_button.Bind(wx.EVT_UPDATE_UI, self.UpdateFinishButton)

        self.button_sizer.Add(self.prev_button, 0, wx.ALL|wx.ALIGN_RIGHT, 5)
        self.button_sizer.Add(self.next_button, 0, wx.ALL|wx.ALIGN_RIGHT, 5)
        self.button_sizer.Add(self.finish_button, 0, wx.ALL|wx.ALIGN_RIGHT, 5)
        self.button_sizer.AddSpacer(10)
        self.button_sizer.Add(self.cancel_button, 0, wx.ALL|wx.ALIGN_RIGHT, 5)
        return self.button_sizer

    def Fit(self):
        self._UpdateSize()
        super(Wizard, self).Fit()

    def AddPage(self, title):
        panel = WizardPage(self.ContentArea, title)
        self.content_sizer.Add(panel, 2, wx.EXPAND)
        self.pages.append(panel)
        if len(self.pages) > 1:
            # hide all panels after the first one
            self.content_sizer.Hide(panel)
        return panel

    def _UpdateSize(self):
        min_w, min_h = 0, 0
        for page in self.pages:
            w, h = page.GetSizer().GetMinSize()
            if w > min_w:
                min_w = w
            if h > min_h:
                min_h = h
        for page in self.pages:
            page.GetSizer().SetMinSize((min_w, min_h))

    def OnNextButton(self, event):
        if self.CanForward():
            self.NextPage()

    def OnPrevButton(self, event):
        if self.CanBack():
            self.PrevPage()

    def GoToPage(self, page):
        if page == self.cur_page:
            return
        if page < 0 or page >= len(self.pages):
            raise ValueError("Invalid page index: {}".format(page))
        old_page, new_page = self.cur_page, page
        self.Freeze()
        self.content_sizer.Hide(old_page)
        self.content_sizer.Show(new_page)
        self.cur_page = new_page
        self.content_sizer.Layout()
        self.Thaw()

    def NextPage(self):
        self.GoToPage(self.cur_page + 1)

    def PrevPage(self):
        self.GoToPage(self.cur_page - 1)

    def OnFinishButton(self, event):
        pass

    def CanBack(self):
        return self.cur_page > 0

    def CanForward(self):
        return self.cur_page < len(self.pages)-1

    def CanApply(self):
        return self.cur_page == len(self.pages)-1

    def UpdatePrevButton(self, event):
        event.Enable(self.CanBack())

    def UpdateNextButton(self, event):
        event.Enable(self.CanForward())

    def UpdateFinishButton(self, event):
        event.Enable(self.CanApply())
