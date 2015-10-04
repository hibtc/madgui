# encoding: utf-8
"""
Widget component to select sequence/range/beam in a model.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core import wx
from madgui.component.beamdialog import BeamWidget
from madgui.component.twissdialog import TwissWidget
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

    Title = "Setup simulation"

    def __init__(self, window, model, madx, utool, **kw):
        self.model = model
        self.madx = madx
        self.utool = utool
        super(ModelDetailWidget, self).__init__(window, **kw)

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
            try:
                combo.Bind(wx.EVT_COMBOBOX_DROPDOWN, panel.OnClick)
            except AttributeError:
                # wx.EVT_COMBOBOX_DROPDOWN not available on windows with wxpython 2.8.12
                pass
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

    def CreateControls(self, window):

        """Create subcontrols and layout."""

        self._book = book = PanelsBook(window)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(book)

        # pages
        page_beam = wx.Panel(book.book)
        page_range = wx.Panel(book.book)
        page_twiss = wx.Panel(book.book)
        self.widget_beam = BeamWidget(page_beam, utool=self.utool)
        self.widget_range = RangeWidget(page_range)
        self.widget_twiss = TwissWidget(page_twiss, utool=self.utool)

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

        book.SetSelection(2)

        return sizer

    def OnSequenceChange(self, event=None):
        """Update default range+beam when sequence is changed."""
        seq_name = self.ctrl_sequence.GetValue()
        self.elements = self.madx.sequences[seq_name].elements
        self.elements_with_units = list(enumerate(
            map(self.utool.dict_add_unit, self.elements)))
        self.UpdateBeams()
        self.UpdateRanges()

    def OnBeamChange(self, event=None):
        data = self.utool.dict_add_unit(self.model['beam'])
        self.widget_beam.SetData(data)

    def OnRangeChange(self, event=None):
        """Update default twiss when range is changed."""
        self.UpdateTwiss()
        beg, end = self.model['range']
        selected = [self.elements.index(beg), self.elements.index(end)]
        self.widget_range.SetData(self.elements_with_units, selected)

    def OnTwissChange(self, event=None):
        twiss_args = self.model['twiss']
        twiss_args = self.utool.dict_add_unit(twiss_args)
        start_element = self.elements.index(self.model['range'][0])
        twiss_initial = twiss_args
        self.widget_twiss.SetData(twiss_initial)

    def GetData(self):
        """Get selected package and model name."""
        return {
            'sequence': self.ctrl_sequence.GetValue(),
            'beam': self.widget_beam.GetData(),
            'range': self.widget_range.GetData(),
            'twiss': self.widget_twiss.GetData(),
            'indicators': self.ctrl_elem.GetValue(),
        }

    def SetData(self, data={}):
        """Update displayed package and model name."""
        self.data = data
        self.UpdateSequences()
        self.ctrl_elem.SetValue(data.get('indicators', True))

    def Validate(self, parent):
        # TODO...
        return True

    def _Update(self, ctrl, items, default, select):
        ctrl.SetItems(list(items))
        try:
            index = items.index(select)
        except ValueError:
            index = items.index(default)
        ctrl.SetSelection(index)

    def UpdateSequences(self):
        # TODO: list all available sequences
        seq_name = self.model['sequence']
        self._Update(self.ctrl_sequence, [seq_name], seq_name, seq_name)
        self.OnSequenceChange()

    def UpdateBeams(self):
        # TODO: list all available beams
        self._Update(self.ctrl_beam,
                     ['default'],
                     'default',
                     'default')
        self.OnBeamChange()

    def UpdateRanges(self):
        # TODO: list all available ranges
        self._Update(self.ctrl_range,
                     ['default'],
                     'default',
                     'default')
        self.OnRangeChange()

    def UpdateTwiss(self):
        self._Update(self.ctrl_twiss,
                     ['default'],
                     'default',
                     'default')
        self.OnTwissChange()
