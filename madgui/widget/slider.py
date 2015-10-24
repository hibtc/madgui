"""
Widget for dual slider.
"""

from __future__ import absolute_import

from .input import Widget
import wx

from wx.lib.newevent import NewCommandEvent


RangeChange, EVT_RANGE_CHANGE = NewCommandEvent()
RangeChangeStart, EVT_RANGE_CHANGE_START = NewCommandEvent()
RangeChangeStop, EVT_RANGE_CHANGE_STOP = NewCommandEvent()


class DualSlider(Widget):

    """
    Widget class to select a range.
    """

    # TODO:
    # - implement in terms of single two-pin slider control

    def CreateControls(self, window):
        self.ctrl_start = start = wx.Slider(window)
        self.ctrl_stop = stop = wx.Slider(window)

        self.sizer = sizer = wx.FlexGridSizer(rows=2, vgap=5, hgap=5)
        sizer.SetFlexibleDirection(wx.HORIZONTAL)

        sizer.Add(start, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.EXPAND)
        sizer.Add(stop, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.EXPAND)

        start.Bind(wx.EVT_SLIDER, self.OnSliderStart)
        stop.Bind(wx.EVT_SLIDER, self.OnSliderStop)
        self.SetMinWidth(100)
        return sizer

    def SetData(self, cur, limits=None):
        if limits is not None:
            min, max = limits
            self.ctrl_start.SetMin(min)
            self.ctrl_stop.SetMin(min)
            self.ctrl_start.SetMax(max)
            self.ctrl_stop.SetMax(max)
        start, stop = cur
        self.ctrl_start.SetValue(start)
        self.ctrl_stop.SetValue(stop)

    def SetMinWidth(self, width):
        self.ctrl_start.SetMinSize((width, -1))
        self.ctrl_stop.SetMinSize((width, -1))

    def GetData(self):
        return (self.ctrl_start.GetValue(),
                self.ctrl_stop.GetValue())

    def OnSliderStart(self, event):
        start, stop = self.GetData()
        self._Post(RangeChangeStart, start=start, stop=stop)
        if start > stop:
            stop = start
            self.ctrl_stop.SetValue(start)
            self._Post(RangeChangeStop, start=start, stop=stop)
        self._Post(RangeChange, start=start, stop=stop)

    def OnSliderStop(self, event):
        start, stop = self.GetData()
        self._Post(RangeChangeStop, start=start, stop=stop)
        if stop < start:
            start = stop
            self.ctrl_start.SetValue(stop)
            self._Post(RangeChangeStart, start=start, stop=stop)
        self._Post(RangeChange, start=start, stop=stop)

    def _Post(self, event_class, **args):
        event = event_class(self.Control.GetId(), **args)
        wx.PostEvent(self.Control.GetEventHandler(), event)
