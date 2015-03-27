# encoding: utf-8
"""
Dialog component to select sequence/range/beam in a model.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core import wx
from madgui.widget.input import ModalDialog
from madgui.widget.bookctrl import PanelsBook


# TODO: show+modify beam and twiss
# TODO: add menu/toolbar for this dialog (?)


class ModelDetailDlg(ModalDialog):

    def SetData(self, model, data=None):
        """Needs a cpymad model and a data dictionary."""
        self.model = model
        self.data = data or {}

    def _AddComboBox(self, label, page):
        """
        Insert combo box with a label into the sizer.

        :param str label: label to be shown to the left
        :returns: the new control
        :rtype: wx.ComboBox
        """
        panel = self._book.AddPage(page)
        label = wx.StaticText(panel, label=label)
        style = wx.CB_READONLY|wx.CB_SORT
        combo = wx.ComboBox(panel, style=style, size=wx.Size(100, -1))
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(label,
                  border=5,
                  flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL)
        sizer.AddStretchSpacer(1)
        sizer.Add(combo,
                  border=5,
                  flag=wx.ALL|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL)
        panel.SetSizer(sizer)
        panel.Finish()
        combo.Bind(wx.EVT_COMBOBOX, panel.OnClick)
        combo.Bind(wx.EVT_COMBOBOX_DROPDOWN, panel.OnClick)
        return combo

    def _AddCheckBox(self, label, page):
        """Insert a check box into the sizer."""
        panel = self._book.AddPage(page)
        ctrl = wx.CheckBox(panel, label=label)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(ctrl, border=5,
                  flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL)
        panel.SetSizer(sizer)
        panel.Finish()
        return ctrl

    def CreateContentArea(self):

        """Create subcontrols and layout."""

        sizer = wx.BoxSizer(wx.VERTICAL)

        self._book = PanelsBook(self)
        sizer.Add(self._book)

        def _CreateDummyPage(label):
            page = wx.Panel(self._book.book)
            page.SetBackgroundColour(wx.Colour(0x7f, 0x7f, 0x7f))
            sizer = wx.BoxSizer(wx.VERTICAL)
            ctrl = wx.StaticText(page, label=label)
            sizer.AddStretchSpacer(1)
            sizer.Add(ctrl, flag=wx.ALL|wx.ALIGN_CENTER_HORIZONTAL, border=10)
            sizer.AddStretchSpacer(1)
            page.SetSizer(sizer)
            return page

        # pages
        page_sequence = _CreateDummyPage("sequence")
        page_beam = _CreateDummyPage("beam")
        page_range = _CreateDummyPage("range")
        page_twiss = _CreateDummyPage("twiss")
        page_style = _CreateDummyPage("style")

        # insert items
        self.ctrl_sequence = self._AddComboBox('Sequence:', page_sequence)
        self.ctrl_beam = self._AddComboBox('Beam:', page_beam)
        self.ctrl_range = self._AddComboBox('Range:', page_range)
        self.ctrl_twiss = self._AddComboBox('Twiss:', page_twiss)
        self.ctrl_elem = self._AddCheckBox('show element indicators', page_style)

        # register for events
        self.Bind(wx.EVT_TEXT, self.OnSequenceChange, source=self.ctrl_sequence)
        self.Bind(wx.EVT_TEXT, self.OnRangeChange, source=self.ctrl_range)

        self._book.SetSelection(0)

        return sizer

    def OnSequenceChange(self, event):
        """Update default range+beam when sequence is changed."""
        self.UpdateBeams()
        self.UpdateRanges()

    def OnRangeChange(self, event):
        """Update default twiss when range is changed."""
        self.UpdateTwiss()

    def TransferDataFromWindow(self):
        """Get selected package and model name."""
        self.data = dict(
            sequence=self.ctrl_sequence.GetValue(),
            beam=self.ctrl_beam.GetValue(),
            range=self.ctrl_range.GetValue(),
            twiss=self.ctrl_twiss.GetValue(),
            indicators=self.ctrl_elem.GetValue(),
        )

    def TransferDataToWindow(self):
        """Update displayed package and model name."""
        self.UpdateSequences()
        self.UpdateBeams()
        self.UpdateRanges()
        self.UpdateTwiss()
        self.ctrl_elem.SetValue(self.data.get('indicators', True))

    def _Update(self, ctrl, items, default, select):
        ctrl.SetItems(list(items))
        try:
            index = items.index(select)
        except ValueError:
            index = items.index(default)
        finally:
            ctrl.SetSelection(index)

    def UpdateSequences(self):
        model, data = self.model, self.data
        self._Update(self.ctrl_sequence,
                     model.sequences.keys(),
                     model.default_sequence.name,
                     data.get('sequence'))

    def UpdateBeams(self):
        model, data = self.model, self.data
        sequence = model.sequences[self.ctrl_sequence.GetValue()]
        self._Update(self.ctrl_beam,
                     model.beams.keys(),
                     sequence.beam.name,
                     data.get('beam'))

    def UpdateRanges(self):
        model, data = self.model, self.data
        sequence = model.sequences[self.ctrl_sequence.GetValue()]
        self._Update(self.ctrl_range,
                     sequence.ranges.keys(),
                     sequence.default_range.name,
                     data.get('range'))

    def UpdateTwiss(self):
        model, data = self.model, self.data
        sequence = model.sequences[self.ctrl_sequence.GetValue()]
        range = sequence.ranges[self.ctrl_range.GetValue()]
        self._Update(self.ctrl_twiss,
                     range.initial_conditions.keys(),
                     range.data['default-twiss'],
                     data.get('twiss'))
