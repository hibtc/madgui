"""
Dialog to select the session settings.
"""

from __future__ import absolute_import

from madgui.component.beamdialog import BeamWidget
from madgui.component.twissdialog import TwissWidget
from madgui.widget.input import Widget
from madgui.widget.choice import ChoiceWidget
from madgui.widget.element import RangeWidget

import wx


__all__ = [
    'SessionWidget',
]


class SessionWidget(Widget):

    def __init__(self, parent, session):
        self.session = session
        super(SessionWidget, self).__init__(parent)

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
        self.w_sequence = w_sequence
        self.w_beam = w_beam
        self.w_twiss = w_twiss
        return sizer

    def SetData(self, mdata):
        self.mdata = mdata
        u = self.session.utool.dict_add_unit
        self.w_beam.SetData(u(self.mdata['beam']))
        self.w_twiss.SetData(u(self.mdata['twiss']))
        self._UpdateSequence()

    def GetData(self):
        sequence, range = self.w_sequence.GetData()
        nu = self.session.utool.dict_strip_unit
        return {
            'sequence': sequence,
            'range': range,
            'beam': nu(self.w_beam.GetData()),
            'twiss': nu(self.w_twiss.GetData()),
        }

    def _UpdateSequence(self):
        self.w_sequence.SetData(self.session.madx, self.mdata, self.session.utool)

    def _UpdateBeam(self):
        # if self.mdata['sequence'] == self.

        self.widget['beam'].SetData(self.mdata['beam'])

    def Validate(self):
        pass

    def _UpdateTwiss(self):
        pass

    def _UpdateSummary(self):
        pass

    def OnFinishButton(self, event):
        pass


class SequenceRangeWidget(Widget):

    def CreateControls(self, window):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.sequence_picker = ChoiceWidget(window, manage=False)
        self.range_picker = RangeWidget(window, manage=False)
        sizer.Add(self.sequence_picker.Control, 0, wx.ALL|wx.ALIGN_TOP, 5)
        sizer.Add(self.range_picker.Control, 1, wx.ALL|wx.ALIGN_TOP, 5)
        self.sequence_picker.Control.Bind(wx.EVT_CHOICE, self.OnChangeSequence)
        return sizer

    def SetData(self, madx, mdata, utool):
        self.madx = madx
        self.mdata = mdata
        self.utool = utool
        self._UpdateSequences()
        self._UpdateRange()

    def OnChangeSequence(self):
        self._UpdateRange()
        ev = wx.PyCommandEvent(wx.EVT_CHOICE.typeId, self.Control.GetId())
        ev.SetString(self.sequence_picker.GetData())
        wx.PostEvent(self.Control.GetEventHandler(), ev)

    def _UpdateSequences(self):
        sequences = list(self.madx.sequences)
        selected_sequence = self.mdata.get('sequence')
        if selected_sequence not in sequences:
            selected_sequence = sequences[0]
        self.sequence_picker.SetData('Sequence:', sequences, selected_sequence)
        self.sequence_picker.ctrl_choices.Bind(wx.EVT_CHOICE, self._UpdateRange)

    def _UpdateRange(self, event=None):
        seq_name = self.sequence_picker.GetData()
        elements = self.madx.sequences[seq_name].elements
        elements_with_units = map(self.utool.dict_add_unit, elements)
        if self.mdata.get('range'):
            beg, end = self.mdata['range']
            selected = [elements.index(beg), elements.index(end)]
        else:
            beg = 0
            end = len(elements) - 1
        self.range_picker.SetData(elements_with_units, selected)

    def GetData(self):
        return (self.sequence_picker.GetData(),
                self.range_picker.GetData())

