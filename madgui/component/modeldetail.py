# encoding: utf-8
"""
Dialog component to select optic/sequence/range/beam in a model.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core import wx


# TODO: show+modify beam and twiss
# TODO: add menu/toolbar for this dialog (?)


class ModelDetailDlg(wx.Dialog):

    def __init__(self, parent, mdef, data=None, **kwargs):
        """Initialize component and create controls."""
        # The mdef dictionary is needed as long as the cpymad Model API is
        # insufficient. Hopefully, this will soon change with the drastical
        # simplifications to the Model/Madx components I have in mind.
        self.mdef = mdef
        self.data = data or {}
        super(ModelDetailDlg, self).__init__(parent, **kwargs)
        self.CreateControls()
        self.Centre()

    def CreateControls(self):

        """Create subcontrols and layout."""

        # Create controls
        label_optic = wx.StaticText(self, label="Optic:")
        label_sequence = wx.StaticText(self, label="Sequence:")
        label_beam = wx.StaticText(self, label="Beam:")
        label_range = wx.StaticText(self, label="Range:")
        label_twiss = wx.StaticText(self, label="Twiss:")
        self.ctrl_optic = wx.ComboBox(self, wx.CB_READONLY|wx.CB_SORT)
        self.ctrl_sequence = wx.ComboBox(self, wx.CB_READONLY|wx.CB_SORT)
        self.ctrl_beam = wx.ComboBox(self, wx.CB_READONLY|wx.CB_SORT)
        self.ctrl_range = wx.ComboBox(self, wx.CB_READONLY|wx.CB_SORT)
        self.ctrl_twiss = wx.ComboBox(self, wx.CB_READONLY|wx.CB_SORT)
        self.TransferDataToWindow() # needed?

        # Create box sizer
        controls = wx.FlexGridSizer(rows=5, cols=2)
        controls.SetFlexibleDirection(wx.HORIZONTAL)
        controls.AddGrowableCol(1, 1)
        controls.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_ALL)

        # insert items
        size = dict(border=5)
        left = dict(size, flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL)
        right = dict(size, flag=wx.ALL|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL)
        controls.Add(label_optic, **left)
        controls.Add(self.ctrl_optic, **right)
        controls.Add(label_sequence, **left)
        controls.Add(self.ctrl_sequence, **right)
        controls.Add(label_beam, **left)
        controls.Add(self.ctrl_beam, **right)
        controls.Add(label_range, **left)
        controls.Add(self.ctrl_range, **right)
        controls.Add(label_twiss, **left)
        controls.Add(self.ctrl_twiss, **right)

        # buttons
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        button_ok = wx.Button(self, wx.ID_OK)
        button_cancel = wx.Button(self, wx.ID_CANCEL)
        buttons.Add(button_ok)
        buttons.Add(button_cancel)

        # outer layout sizer
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(controls, flag=wx.ALIGN_CENTER_VERTICAL|wx.EXPAND|wx.ALL, **size)
        outer.Add(buttons, flag=wx.ALIGN_CENTER_HORIZONTAL|wx.ALL, **size)

        # register for events
        self.Bind(wx.EVT_TEXT, self.OnSequenceChange, source=self.ctrl_sequence)
        self.Bind(wx.EVT_TEXT, self.OnRangeChange, source=self.ctrl_range)
        self.Bind(wx.EVT_BUTTON, self.OnButtonOk, source=button_ok)
        self.Bind(wx.EVT_BUTTON, self.OnButtonCancel, source=button_cancel)

        # associate sizer and layout
        self.SetSizer(outer)
        outer.Fit(self)

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
            optic=self.ctrl_optic.GetValue(),
            sequence=self.ctrl_sequence.GetValue(),
            beam=self.ctrl_beam.GetValue(),
            range=self.ctrl_range.GetValue(),
            twiss=self.ctrl_twiss.GetValue())

    def TransferDataToWindow(self):
        """Update displayed package and model name."""
        self.UpdateOptics()
        self.UpdateSequences()
        self.UpdateBeams()
        self.UpdateRanges()
        self.UpdateTwiss()

    def _Update(self, ctrl, items, default, select):
        ctrl.SetItems(list(items))
        try:
            index = items.index(select)
        except ValueError:
            index = items.index(default)
        finally:
            ctrl.SetSelection(index)

    def UpdateOptics(self):
        mdef, data = self.mdef, self.data
        self._Update(self.ctrl_optic,
                     mdef['optics'].keys(), 
                     mdef['default-optic'],
                     data.get('optic'))

    def UpdateSequences(self):
        mdef, data = self.mdef, self.data
        self._Update(self.ctrl_sequence,
                     mdef['sequences'].keys(), 
                     mdef['default-sequence'],
                     data.get('sequence'))

    def UpdateBeams(self):
        mdef, data = self.mdef, self.data
        sdef = mdef['sequences'][self.ctrl_sequence.GetValue()]
        self._Update(self.ctrl_beam,
                     mdef['beams'].keys(), 
                     sdef['beam'],
                     data.get('sequence'))

    def UpdateRanges(self):
        mdef, data = self.mdef, self.data
        sdef = mdef['sequences'][self.ctrl_sequence.GetValue()]
        self._Update(self.ctrl_range,
                     sdef['ranges'].keys(), 
                     sdef['default-range'],
                     data.get('range'))

    def UpdateTwiss(self):
        mdef, data = self.mdef, self.data
        sdef = mdef['sequences'][self.ctrl_sequence.GetValue()]
        rdef = sdef['ranges'][self.ctrl_range.GetValue()]
        self._Update(self.ctrl_twiss,
                     rdef['twiss-initial-conditions'].keys(), 
                     rdef['default-twiss'],
                     data.get('twiss'))

    def OnButtonOk(self, event):
        """Confirm current selection and close dialog."""
        self.TransferDataFromWindow()
        self.EndModal(wx.ID_OK)

    def OnButtonCancel(self, event):
        """Cancel the dialog."""
        self.EndModal(wx.ID_CANCEL)
