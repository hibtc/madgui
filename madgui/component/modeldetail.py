# encoding: utf-8
"""
Dialog component to select optic/sequence/range/beam in a model.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core import wx
from madgui.core.input import ModalDialog


# TODO: show+modify beam and twiss
# TODO: add menu/toolbar for this dialog (?)


class ModelDetailDlg(ModalDialog):

    def SetData(self, mdef, data=None):
        # The mdef dictionary is needed as long as the cpymad Model API is
        # insufficient. Hopefully, this will soon change with the drastical
        # simplifications to the Model/Madx components I have in mind.
        self.mdef = mdef
        self.data = data or {}


    def _AddComboBox(self, sizer, label):
        """
        Insert combo box with a label into the sizer.

        :param wx.FlexGridSizer sizer: 2-columns
        :param str label: label to be shown to the left
        :returns: the new control
        :rtype: wx.ComboBox
        """
        label = wx.StaticText(self, label=label)
        combo = wx.ComboBox(self, wx.CB_READONLY|wx.CB_SORT)
        sizer.Add(label,
                  border=5,
                  flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(combo,
                  border=5,
                  flag=wx.ALL|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL)
        return combo

    def CreateControls(self):

        """Create subcontrols and layout."""

        # Create box sizer
        controls = wx.FlexGridSizer(rows=5, cols=2)
        controls.SetFlexibleDirection(wx.HORIZONTAL)
        controls.AddGrowableCol(1, 1)
        controls.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_ALL)

        # insert items
        self.ctrl_optic = self._AddComboBox(controls, 'Optic:')
        self.ctrl_sequence = self._AddComboBox(controls, 'Sequence:')
        self.ctrl_beam = self._AddComboBox(controls, 'Beam:')
        self.ctrl_range = self._AddComboBox(controls, 'Range:')
        self.ctrl_twiss = self._AddComboBox(controls, 'Twiss:')
        self.TransferDataToWindow() # needed?

        # outer layout sizer
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(controls,
                  border=5,
                  flag=wx.ALIGN_CENTER_VERTICAL|wx.EXPAND|wx.ALL)
        outer.Add(self.CreateButtonSizer(),
                  border=5,
                  flag=wx.ALIGN_CENTER_HORIZONTAL|wx.ALL)

        # register for events
        self.Bind(wx.EVT_TEXT, self.OnSequenceChange, source=self.ctrl_sequence)
        self.Bind(wx.EVT_TEXT, self.OnRangeChange, source=self.ctrl_range)

        # associate sizer and layout
        self.SetSizer(outer)

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
