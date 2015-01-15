# encoding: utf-8
"""
Dialog component to select sequence/range/beam in a model.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core import wx
from madgui.widget.input import ModalDialog


# TODO: show+modify beam and twiss
# TODO: add menu/toolbar for this dialog (?)


class ModelDetailDlg(ModalDialog):

    def SetData(self, model, data=None):
        """Needs a cpymad model and a data dictionary."""
        self.model = model
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

    def _AddCheckBox(self, sizer, label):
        """Insert a check box into the sizer."""
        ctrl = wx.CheckBox(self, label=label)
        sizer.AddSpacer(10)
        sizer.Add(ctrl, border=5,
                  flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL)
        return ctrl

    def CreateContentArea(self):

        """Create subcontrols and layout."""

        # Create box sizer
        controls = wx.FlexGridSizer(rows=5, cols=2)
        controls.SetFlexibleDirection(wx.HORIZONTAL)
        controls.AddGrowableCol(1, 1)
        controls.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_ALL)

        # insert items
        self.ctrl_sequence = self._AddComboBox(controls, 'Sequence:')
        self.ctrl_beam = self._AddComboBox(controls, 'Beam:')
        self.ctrl_range = self._AddComboBox(controls, 'Range:')
        self.ctrl_twiss = self._AddComboBox(controls, 'Twiss:')
        self.ctrl_elem = self._AddCheckBox(controls, 'show element indicators')

        # register for events
        self.Bind(wx.EVT_TEXT, self.OnSequenceChange, source=self.ctrl_sequence)
        self.Bind(wx.EVT_TEXT, self.OnRangeChange, source=self.ctrl_range)

        return controls

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
