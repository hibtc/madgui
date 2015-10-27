"""
Dialog to edit the current model.
"""

from __future__ import absolute_import

from madgui.component.beamdialog import BeamWidget
from madgui.component.twissdialog import TwissWidget
from madgui.widget.input import Widget
from madgui.widget.choice import ChoiceWidget
from madgui.widget.element import RangeWidget

import wx


__all__ = [
    'ModelWidget',
]


class ModelWidget(Widget):

    """
    Model config dialog.

    Allows to view and modify the following model properties:

        - sequence and range
        - beam properties
        - twiss initial conditions
    """

    def __init__(self, parent, session):
        self.session = session
        super(ModelWidget, self).__init__(parent)

    def CreateControls(self, window):
        sizer = wx.BoxSizer(wx.VERTICAL)
        w_sequence = SequenceRangeWidget(window, manage=False)
        w_beam = BeamWidget(window, manage=False, utool=self.session.utool)
        w_twiss = TwissWidget(window, manage=False, utool=self.session.utool)
        l_sequence = wx.StaticText(window, label="Select sequence and range")
        l_beam = wx.StaticText(window, label="Set beam properties")
        l_twiss = wx.StaticText(window, label="Set TWISS initial conditions")
        sizer.Add(l_sequence, 0, wx.ALL|wx.ALIGN_LEFT, 5)
        sizer.Add(w_sequence.Control, 0, wx.ALL|wx.EXPAND, 5)
        sizer.Add(wx.StaticLine(window, style=wx.LI_HORIZONTAL), 0, wx.EXPAND)
        sizer.Add(l_beam, 0, wx.ALL|wx.ALIGN_LEFT, 5)
        sizer.Add(w_beam.Control, 1, wx.ALL|wx.EXPAND, 5)
        sizer.Add(wx.StaticLine(window, style=wx.LI_HORIZONTAL), 0, wx.EXPAND)
        sizer.Add(l_twiss, 0, wx.ALL|wx.ALIGN_LEFT, 5)
        sizer.Add(w_twiss.Control, 1, wx.ALL|wx.EXPAND, 5)
        w_sequence.Control.Bind(wx.EVT_CHOICE, self.OnChangeSequence)
        self.w_sequence = w_sequence
        self.w_beam = w_beam
        self.w_twiss = w_twiss
        return sizer

    def OnChangeSequence(self, event=None):
        """
        Update UI controls after changing the sequence selection using the
        most suitable known model data for the given sequence.
        """
        session = self.session
        sequence, _ = self.w_sequence.GetData()
        if self.mdata.get('sequence') == sequence:
            mdata = self.mdata
        else:
            mdata = session._get_seq_model(sequence)
        self.w_sequence._UpdateRange()
        self.w_beam.SetData(mdata.get('beam', {}))
        self.w_twiss.SetData(mdata.get('twiss', {}))

    def SetData(self, mdata):
        """Set the current model {sequence, range, beam, twiss} dict."""
        self.mdata = mdata
        self.w_sequence.SetData(self.session.madx, self.session.utool,
                                sequence=mdata.get('sequence'),
                                range=mdata.get('range'))
        self.OnChangeSequence()

    def GetData(self):
        """Get a model dict with {sequence, range, beam, twiss} fields."""
        sequence, range = self.w_sequence.GetData()
        return {
            'sequence': sequence,
            'range': range,
            'beam': self.w_beam.GetData(),
            'twiss': self.w_twiss.GetData(),
        }

    def Validate(self):
        """Validate the current state of the control."""
        return (self.w_sequence.Validate() and
                self.w_beam.Validate() and
                self.w_twiss.Validate())


class SequenceRangeWidget(Widget):

    """
    Allows to select

    - the sequence (among all sequences currently defined in MAD-X)
    - the range within the selected sequence (via elements defined in MAD-X)
    """

    def CreateControls(self, window):
        """Create sub-controls."""
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.sequence_picker = ChoiceWidget(window, manage=False)
        self.range_picker = RangeWidget(window, manage=False)
        sizer.Add(self.sequence_picker.Control, 0, wx.ALL|wx.ALIGN_TOP, 5)
        sizer.Add(self.range_picker.Control, 1, wx.ALL|wx.ALIGN_TOP, 5)
        self.sequence_picker.Control.Bind(wx.EVT_CHOICE, self.OnChangeSequence)
        return sizer

    def SetData(self, madx, utool, sequence, range):
        """Set the control state."""
        self.madx = madx
        self.utool = utool
        self.sequence = sequence
        self.range = range
        self._UpdateSequences()
        self._UpdateRange()

    def OnChangeSequence(self):
        """
        Act upon changed sequence selection: Update the range and propagate an
        event upwards.
        """
        self._UpdateRange()
        ev = wx.PyCommandEvent(wx.EVT_CHOICE.typeId, self.Control.GetId())
        ev.SetString(self.sequence_picker.GetData())
        wx.PostEvent(self.Control.GetEventHandler(), ev)

    def _UpdateSequences(self):
        """Update list of shown sequences."""
        sequences = list(self.madx.sequences)
        selected_sequence = self.sequence
        if selected_sequence not in sequences:
            selected_sequence = sequences[0]
        self.sequence_picker.SetData('Sequence:', sequences, selected_sequence)
        self.sequence_picker.ctrl_choices.Bind(wx.EVT_CHOICE, self._UpdateRange)

    def _UpdateRange(self, event=None):
        """Update list of elements in range selection control."""
        seq_name = self.sequence_picker.GetData()
        elements = self.madx.sequences[seq_name].elements
        elements_with_units = map(self.utool.dict_add_unit, elements)
        if self.sequence == seq_name and self.range:
            beg, end = self.range
            selected = [elements.index(beg), elements.index(end)]
        else:
            beg = 0
            end = len(elements) - 1
            selected = [beg, end]
        self.range_picker.SetData(elements_with_units, selected)

    def GetData(self):
        """Return (seq_name, range) with range of the form (start, stop)."""
        return (self.sequence_picker.GetData(),
                self.range_picker.GetData())

    def Validate(self):
        """Check that the current state of the control sense."""
        return (self.sequence_picker.Validate() and
                self.range_picker.Validate())
