# encoding: utf-8
"""
Widget component to select sequence/range/beam in a model.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core import wx
from madgui.component.beamdialog import BeamWidget
from madgui.component.twissdialog import ManageTwissWidget
from madgui.util.common import instancevars
from madgui.widget.input import Widget
from madgui.widget.element import RangeWidget
from madgui.widget.bookctrl import PanelsBook

# exported symbols
__all__ = [
    'ModelDetailWidget',
]


# TODO: show+modify beam and twiss
# TODO: add menu/toolbar for this dialog (?)


class ModelDetailWidget(Widget):

    title = "Setup simulation"

    @instancevars
    def __init__(self, model, data, utool):
        pass

    def _AddComboBox(self, label, page=None):
        """
        Insert combo box with a label into the sizer.

        :param str label: label to be shown to the left
        :returns: the new control
        :rtype: wx.ComboBox
        """
        if page:
            panel = self._book.AddPage(page)
        else:
            panel = wx.Panel(self._book.menu)
            self._book.menu._sizer.Add(panel, flag=wx.EXPAND)
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
        if page:
            panel.Finish()
            combo.Bind(wx.EVT_COMBOBOX, panel.OnClick)
            combo.Bind(wx.EVT_COMBOBOX_DROPDOWN, panel.OnClick)
        return combo

    def _AddCheckBox(self, label):
        """Insert a check box into the sizer."""
        panel = wx.Panel(self._book.menu)
        self._book.menu._sizer.Add(panel, flag=wx.EXPAND)
        ctrl = wx.CheckBox(panel, label=label)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(ctrl, border=5,
                  flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL)
        panel.SetSizer(sizer)
        return ctrl

    def CreateControls(self):

        """Create subcontrols and layout."""

        window = self.GetWindow()

        sizer = wx.BoxSizer(wx.VERTICAL)

        self._book = PanelsBook(window)
        sizer.Add(self._book)

        utool = self.utool

        self.widget_beam = BeamWidget(utool=utool, data={})
        self.widget_range = RangeWidget(elements=[], selected=[])
        self.widget_twiss = ManageTwissWidget(utool=utool, elements=[],
                                              data={}, inactive={})

        # pages
        page_beam = self.widget_beam.EmbedPanel(self._book.book)
        page_range = self.widget_range.EmbedPanel(self._book.book)
        page_twiss = self.widget_twiss.EmbedPanel(self._book.book)

        # insert items
        self.ctrl_sequence = self._AddComboBox('Sequence:')
        self.ctrl_range = self._AddComboBox('Range:', page_range)
        self.ctrl_beam = self._AddComboBox('Beam:', page_beam)
        self.ctrl_twiss = self._AddComboBox('Twiss:', page_twiss)
        self.ctrl_elem = self._AddCheckBox('show element indicators')

        # register for events
        window.Bind(wx.EVT_COMBOBOX, self.OnSequenceChange, source=self.ctrl_sequence)
        window.Bind(wx.EVT_COMBOBOX, self.OnBeamChange, source=self.ctrl_beam)
        window.Bind(wx.EVT_COMBOBOX, self.OnRangeChange, source=self.ctrl_range)
        window.Bind(wx.EVT_COMBOBOX, self.OnTwissChange, source=self.ctrl_twiss)

        # window.Bind(wx.EVT_TEXT, self.OnSequenceChange, source=self.ctrl_sequence)
        # window.Bind(wx.EVT_TEXT, self.OnRangeChange, source=self.ctrl_range)

        self._book.SetSelection(2)

        return sizer

    def OnSequenceChange(self, event=None):
        """Update default range+beam when sequence is changed."""
        self.UpdateBeams()
        self.UpdateRanges()

    def OnBeamChange(self, event=None):
        utool = self.utool
        beam = self.ctrl_beam.GetValue()
        data = self.model.beams[beam].data
        data = utool.dict_add_unit(data)
        self.widget_beam.__init__(utool=utool, data=data)
        self.widget_beam.TransferToWindow()

    def OnRangeChange(self, event=None):
        """Update default twiss when range is changed."""
        self.UpdateTwiss()
        model = self.model
        seq_name = self.ctrl_sequence.GetValue()
        sequence = model.sequences[seq_name]
        range = sequence.ranges[self.ctrl_range.GetValue()]
        elements = model.madx.sequences[seq_name].elements
        beg, end = range.bounds
        selected = [elements.index(beg), elements.index(end)]
        self.widget_range.elements[:] = enumerate(elements)
        self.widget_range.selected[:] = selected
        self.widget_range.TransferToWindow()

    def OnTwissChange(self, event=None):
        model = self.model
        seq_name = self.ctrl_sequence.GetValue()
        sequence = model.sequences[seq_name]
        range = sequence.ranges[self.ctrl_range.GetValue()]
        twiss_name = self.ctrl_twiss.GetValue()
        twiss_args = range.initial_conditions[twiss_name]
        twiss_args = self.utool.dict_add_unit(twiss_args)
        elements = model.madx.sequences[seq_name].elements
        start_element = elements.index(range.bounds[0])
        twiss_initial = {start_element: twiss_args}
        self.widget_twiss.elements[:] = map(self.utool.dict_add_unit,
                                            elements)
        self.widget_twiss.data.clear()
        self.widget_twiss.data.update(twiss_initial)
        self.widget_twiss.inactive.clear()
        self.widget_twiss.TransferToWindow()

    def TransferFromWindow(self):
        """Get selected package and model name."""
        self.widget_beam.TransferFromWindow()
        self.widget_range.TransferFromWindow()
        self.widget_twiss.TransferFromWindow()
        self.data.update(
            sequence=self.ctrl_sequence.GetValue(),
            beam=self.widget_beam.data,
            range=self.widget_range.selected,
            twiss=self.widget_twiss.data,
            indicators=self.ctrl_elem.GetValue(),
        )

    def TransferToWindow(self):
        """Update displayed package and model name."""
        self.UpdateSequences()
        self.ctrl_elem.SetValue(self.data.get('indicators', True))

    def Validate(self, parent):
        # TODO...
        return True

    # TODO: using 'self.data' for 'select' is flawed (unless
    # TransferFromWindow is executed here and then)
    def _Update(self, ctrl, items, default, select):
        ctrl.SetItems(list(items))
        try:
            index = items.index(select)
        except ValueError:
            index = items.index(default)
        ctrl.SetSelection(index)

    def UpdateSequences(self):
        model, data = self.model, self.data
        self._Update(self.ctrl_sequence,
                     model.sequences.keys(),
                     model.default_sequence.name,
                     data.get('sequence'))
        self.OnSequenceChange()

    def UpdateBeams(self):
        model, data = self.model, self.data
        sequence = model.sequences[self.ctrl_sequence.GetValue()]
        self._Update(self.ctrl_beam,
                     model.beams.keys(),
                     sequence.beam.name,
                     data.get('beam'))
        self.OnBeamChange()

    def UpdateRanges(self):
        model, data = self.model, self.data
        sequence = model.sequences[self.ctrl_sequence.GetValue()]
        self._Update(self.ctrl_range,
                     sequence.ranges.keys(),
                     sequence.default_range.name,
                     data.get('range'))
        self.OnRangeChange()

    def UpdateTwiss(self):
        model, data = self.model, self.data
        sequence = model.sequences[self.ctrl_sequence.GetValue()]
        range = sequence.ranges[self.ctrl_range.GetValue()]
        self._Update(self.ctrl_twiss,
                     range.initial_conditions.keys(),
                     range.data['default-twiss'],
                     data.get('twiss'))
        self.OnTwissChange()
