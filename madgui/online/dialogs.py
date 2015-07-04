"""
Dialog for selecting DVM parameters to be synchronized.
"""

from __future__ import absolute_import

from functools import partial

from madgui.core import wx
from madgui.widget.listview import ListCtrl, ColumnInfo
from madgui.widget.input import Widget
from madgui.widget.element import ElementWidget
from madgui.util.unit import format_quantity, tounit


def el_names(elems):
    return [el['name'] for el in elems]


class ListSelectWidget(Widget):

    """
    Widget for selecting from an immutable list of items.
    """

    _min_size = wx.Size(400, 300)
    _headline = 'Select desired items:'

    # TODO: allow to customize initial selection
    # FIXME: select-all looks ugly, check/uncheck-each is tedious...

    def CreateControls(self, window):
        """Create sizer with content area, i.e. input fields."""
        grid = ListCtrl(window, self.GetColumns(), style=0)
        grid.SetMinSize(self._min_size)
        self._grid = grid
        # create columns
        # other layout
        headline = wx.StaticText(window, label=self._headline)
        inner = wx.BoxSizer(wx.HORIZONTAL)
        inner.Add(grid, 1, flag=wx.ALL|wx.EXPAND, border=5)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(headline, flag=wx.ALL|wx.ALIGN_LEFT, border=5)
        outer.Add(inner, 1, flag=wx.ALL|wx.EXPAND, border=5)
        return outer

    def SetData(self, data):
        self._grid.items = data
        # TODO: replace SELECT(ALL) by SELECT(SELECTED)
        for idx in range(len(data)):
            self._grid.Select(idx)

    def GetData(self):
        return list(self._grid.selected_items)


def format_dvm_value(param, value):
    value = tounit(value, param.dvm_param.ui_unit)
    fmt_code = '.{}f'.format(param.dvm_param.ui_prec)
    return format_quantity(value, fmt_code)


class SyncParamWidget(ListSelectWidget):

    """
    Dialog for selecting DVM parameters to be synchronized.
    """

    def GetColumns(self):
        return [
            ColumnInfo(
                "Param",
                self._format_param,
                wx.LIST_FORMAT_LEFT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "DVM value",
                self._format_dvm_value,
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "MAD-X value",
                self._format_madx_value,
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
        ]

    def _format_param(self, index, item):
        param, dvm_value = item
        return param.dvm_name

    def _format_dvm_value(self, index, item):
        param, dvm_value = item
        return format_dvm_value(param, dvm_value)

    def _format_madx_value(self, index, item):
        param, dvm_value = item
        mad_value = param.madx2dvm(param.mad_value)
        return format_dvm_value(param, mad_value)


class ImportParamWidget(SyncParamWidget):
    Title = 'Import parameters from DVM'
    headline = 'Import selected DVM parameters.'


class ExportParamWidget(SyncParamWidget):
    Title = 'Set values in DVM from current sequence'
    headline = 'Overwrite selected DVM parameters.'


class MonitorWidget(ListSelectWidget):

    """
    Dialog for selecting SD monitor values to be imported.
    """

    Title = 'Set values in DVM from current sequence'

    _headline = "Import selected monitor measurements:"

    def GetColumns(self):
        return [
            ColumnInfo(
                "Monitor",
                self._format_monitor_name,
                wx.LIST_FORMAT_LEFT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "x",
                partial(self._format_sd_value, 'posx'),
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "y",
                partial(self._format_sd_value, 'posy'),
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "x width",
                partial(self._format_sd_value, 'widthx'),
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "y width",
                partial(self._format_sd_value, 'widthy'),
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
        ]

    def _format_monitor_name(self, index, item):
        elem, values = item
        return elem['name']

    def _format_sd_value(self, name, index, item):
        elem, values = item
        value = values.get(name)
        if value is None:
            return ''
        return format_quantity(value)


def NumericInputCtrl(window):
    return wx.TextCtrl(window, style=wx.TE_RIGHT)


def _is_steerer(el):
    return el['type'] == 'sbend' \
        or el['type'] == 'multipole' and (
            el['knl'][0] != 0 or
            el['ksl'][0] != 0)


class OpticSelectWidget(Widget):

    """
    Select elements for "optik-varianz" method.
    """

    def CreateControls(self, window):
        sizer = wx.FlexGridSizer(7, 3)
        sizer.AddGrowableCol(1)
        def _Add(label):
            ctrl = wx.Choice(window)
            sizer.Add(wx.StaticText(window, label=label), border=5,
                      flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL)
            sizer.AddSpacer(10)
            sizer.Add(ctrl, border=5,
                      flag=wx.ALL|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL)
            return ctrl
        self.ctrl_mon = _Add("Monitor:")
        self.ctrl_qps = (_Add("Quadrupole 1:"), _Add("Quadrupole 2:"))
        self.ctrl_hst = (_Add("H-Steerer 1:"), _Add("H-Steerer 2:"))
        self.ctrl_vst = (_Add("V-Steerer 1:"), _Add("V-Steerer 2:"))
        self.ctrl_mon.Bind(wx.EVT_CHOICE, self.OnChangeMonitor)
        outer = wx.BoxSizer(wx.VERTICAL)
        text = "Select elements for beam alignment:"
        outer.Add(wx.StaticText(window, label=text), flag=wx.ALL, border=5)
        outer.Add(sizer, 1, flag=wx.ALL|wx.EXPAND, border=5)
        return outer

    def OnChangeMonitor(self, event=None):
        try:
            conf = self.config[self.ctrl_mon.GetStringSelection().upper()]
        except KeyError:
            return
        elem_ctrls = self.ctrl_qps + self.ctrl_hst + self.ctrl_vst
        elem_names = conf['qp'] + conf['h-steerer'] + conf['v-steerer']
        for ctrl, name in zip(elem_ctrls, elem_names):
            ctrl.SetStringSelection(name.lower())

    def GetData(self):
        mon = self.ctrl_mon.GetStringSelection()
        qps = tuple(c.GetStringSelection() for c in self.ctrl_qps)
        hst = tuple(c.GetStringSelection() for c in self.ctrl_hst)
        vst = tuple(c.GetStringSelection() for c in self.ctrl_vst)
        return mon, qps, hst, vst

    def SetData(self, elements, config):
        # TODO: check config (length/content of individual fields)
        self.config = config
        self.elem_mon = [el for el in elements
                         if el['type'].endswith('monitor')]
        self.elem_qps = [el for el in elements
                         if el['type'] == 'quadrupole']
        self.elem_dip = [el for el in elements
                         if _is_steerer(el)]
        self.ctrl_mon.SetItems(el_names(self.elem_mon))
        for ctrl in self.ctrl_qps:
            ctrl.SetItems(el_names(self.elem_qps))
        for ctrl in self.ctrl_hst + self.ctrl_vst:
            ctrl.SetItems(el_names(self.elem_dip))
        # TODO: remember selection
        if config:
            sel = max(self.ctrl_mon.FindString(mon.lower()) for mon in config)
        else:
            sel = len(self.elem_mon) - 1
        self.ctrl_mon.SetSelection(sel)
        self.OnChangeMonitor()

    def Validate(self, window):
        sel_mon = self.ctrl_mon.GetSelection()
        sel_qp = tuple(ctrl.GetSelection() for ctrl in self.ctrl_qps)
        sel_st = tuple(ctrl.GetSelection() for ctrl in self.ctrl_hst + self.ctrl_vst)
        def _at(sel, elems):
            if sel == wx.NOT_FOUND:
                raise ValueError
            return elems[sel]['at']
        try:
            at_mon = _at(sel_mon, self.elem_mon)
            at_qp = [_at(sel, self.elem_qps) for sel in sel_qp]
            at_st = [_at(sel, self.elem_dip) for sel in sel_st]
        except ValueError:
            return False
        return all(at <= at_mon for at in at_qp + at_st)



class OptikVarianzWidget(Widget):

    """
    Dialog to perform "Optik Varianz" method for transversal beam alignment.
    """

    # TODO: make this a dialog / wizard?

    # TODO: first implement without "Load from focus" option

    def CreateControls(self, window):

        sizer = wx.BoxSizer(wx.VERTICAL)
        phys_group = wx.FlexGridSizer(5, 4)
        calc_group = wx.BoxSizer(wx.HORIZONTAL)
        butt_group = wx.BoxSizer(wx.VERTICAL)

        def _Add(_label, cls, *args, **kwargs):
            ctrl1 = cls(window, *args, **kwargs)
            ctrl2 = cls(window, *args, **kwargs)
            phys_group.Add(wx.StaticText(window, label=_label), border=5,
                      flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL)
            phys_group.AddSpacer(10)
            phys_group.Add(ctrl1, border=5,
                      flag=wx.ALL|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL)
            phys_group.Add(ctrl2, border=5,
                      flag=wx.ALL|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL)
            return ctrl1, ctrl2

        self.ctrls_qp = (
            _Add("QP 1", wx.TextCtrl),
            _Add("QP 2", wx.TextCtrl),
        )
        self.ctrl_use = (
            _Add("", wx.Button, label="Use")
        )
        self.ctrl_mon = (
            _Add("Beam X", wx.TextCtrl, style=wx.TE_READONLY),
            _Add("Beam Y", wx.TextCtrl, style=wx.TE_READONLY),
        )

        calculated = wx.ListCtrl(window)

        sizer.Add(phys_group, flag=wx.ALL|wx.EXPAND, border=5)
        sizer.Add(calc_group, flag=wx.ALL|wx.EXPAND, border=5)
        calc_group.Add(calculated, 1, flag=wx.ALL|wx.EXPAND, border=5)
        calc_group.Add(butt_group, flag=wx.ALL, border=5)
        butt_group.Add(wx.Button(window, wx.ID_APPLY), flag=wx.ALL, border=5)
        butt_group.Add(wx.Button(window, wx.ID_CLOSE), flag=wx.ALL, border=5)
        return sizer

    def GetData(self):
        pass

    def SetData(self, plugin, mon, qps, hst, vst):
        self.plugin = plugin
        self.mon = mon
        self.qps = qps
        self.hst = hst
        self.vst = vst

    def OnReadQPs(self, event):
        pass

    def OnSetQPs(self, event):
        pass

    def OnReadMon(self, event):
        pass

    def OnApply(self, event):
        kl_0 = segment.session.utool.add_unit('kl', kl_0)
        kl_1 = segment.session.utool.add_unit('kl', kl_1)
        self.sync_from_db()
        tw = self.find_initial_position(mon, qp, kl_0, kl_1)
        # TODO: proper update via segment methods
        segment.twiss_args.update(tw)
        segment.twiss()
        # align_beam(mon)
