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


def incomplete(l):
    return any(x is None for x in l)


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
        #for idx in range(len(data)):
        #    self._grid.Select(idx)

    def GetData(self):
        return list(self._grid.selected_items)


def format_dvm_value(param, value):
    value = tounit(value, param.ui_unit)
    fmt_code = '.{}f'.format(param.ui_prec)
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
        param, dvm_value, mad_value = item
        return param.name

    def _format_dvm_value(self, index, item):
        param, dvm_value, mad_value = item
        return format_dvm_value(param, dvm_value)

    def _format_madx_value(self, index, item):
        param, dvm_value, mad_value = item
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
        el_name, values = item
        return el_name

    def _format_sd_value(self, name, index, item):
        el_name, values = item
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
        phys_group = wx.FlexGridSizer(6, 4)
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

        # TODO: show units!
        self.ctrls_qp = (
            _Add("QP 1", wx.TextCtrl),
            _Add("QP 2", wx.TextCtrl),
        )
        self.ctrl_set = (
            _Add("", wx.Button, label="Set")
        )
        self.ctrl_read = (
            _Add("", wx.Button, label="Read")
        )
        self.ctrl_mon = (
            _Add("Beam X", wx.TextCtrl, style=wx.TE_READONLY),
            _Add("Beam Y", wx.TextCtrl, style=wx.TE_READONLY),
        )

        self.ctrl_apply = wx.Button(window, wx.ID_APPLY)
        self.ctrl_close = wx.Button(window, wx.ID_CLOSE)

        self.ctrl_set[0].Bind(wx.EVT_BUTTON, partial(self.OnSetQP, run_id=0))
        self.ctrl_set[1].Bind(wx.EVT_BUTTON, partial(self.OnSetQP, run_id=1))
        self.ctrl_read[0].Bind(wx.EVT_BUTTON, partial(self.OnProbe, run_id=0))
        self.ctrl_read[1].Bind(wx.EVT_BUTTON, partial(self.OnProbe, run_id=1))

        self.ctrl_apply.Bind(wx.EVT_BUTTON, self.OnApply)
        self.ctrl_apply.Bind(wx.EVT_UPDATE_UI, self.OnApplyUpdate)

        calculated = wx.ListCtrl(window)

        sizer.Add(phys_group, flag=wx.ALL|wx.EXPAND, border=5)
        sizer.Add(calc_group, flag=wx.ALL|wx.EXPAND, border=5)
        calc_group.Add(calculated, 1, flag=wx.ALL|wx.EXPAND, border=5)
        calc_group.Add(butt_group, flag=wx.ALL, border=5)
        butt_group.Add(self.ctrl_apply, flag=wx.ALL, border=5)
        butt_group.Add(self.ctrl_close, flag=wx.ALL, border=5)

        return sizer

    def OnSetQP(self, event, run_id):
        for qp_id, qp_name in enumerate(self.qps):
            qp_elem = self.control.get_element(qp_name)
            qp_value = float(self.ctrls_qp[qp_id][run_id].GetValue())
            qp_value = self.utool.add_unit('kL', qp_value)
            values = {'kL': qp_value}
            qp_elem.mad_backend.set(qp_elem.mad_converter.to_backend(values))
            qp_elem.dvm_backend.set(qp_elem.dvm_converter.to_backend(values))
        self.plugin.execute()

    def OnProbe(self, event, run_id):
        mon_name = self.mon
        mon_elem = self.control.get_element(mon_name)
        mon_info = self.segment.get_element_info(mon_name)
        self.sectormap[run_id] = self.segment.get_transfer_map(
            self.segment.start, mon_info)
        self.measure[run_id] = values = mon_elem.dvm_converter.to_standard(
            mon_elem.dvm_backend.get())
        self.ctrl_mon[0][run_id].SetValue(format_quantity(values['posx']))
        self.ctrl_mon[1][run_id].SetValue(format_quantity(values['posy']))
        self.UpdateCalculation()

    def GetData(self):
        pass

    def SetData(self, control, mon, qps, hst, vst):
        self.control = control
        self.mon = mon
        self.qps = qps
        self.hst = hst
        self.vst = vst
        # dialog state
        self.sectormap = [None, None]
        self.measure = [None, None]
        self.init_twiss = None
        self.steerer_corrections = None
        # convenience aliases
        self.plugin = control._plugin
        self.segment = segment = control._segment
        self.utool = segment.utool
        self.madx = segment.madx
        # TODO: self.sync_from_db()


    def OnApply(self, event):
        for el, vals in self.steerer_corrections:
            el.mad_backend.set(vals)
            el.dvm_backend.set(el.mad2dvm(vals))
        self.plugin.execute()
        # self.segment.twiss()

    def OnApplyUpdate(self, event):
        event.Enable(bool(self.steerer_corrections))

    def UpdateCalculation(self):
        if incomplete(self.sectormap) or incomplete(self.measure):
            return

        steerer_names = self.hst + self.vst
        steerer_elems = [self.control.get_element(v) for v in steerer_names]

        # backup  MAD-X values
        steerer_values = [el.mad_backend.get() for el in steerer_elems]

        # compute initial condition
        self.init_twiss = init_twiss = {}
        init_twiss.update(self.segment.twiss_args)
        init_twiss.update(self.control.compute_initial_position(
            self.sectormap[0],
            self.measure[0],
            self.sectormap[1],
            self.measure[1],
        ))
        self.segment._twiss_args = init_twiss

        # match final conditions
        constraints = [
            {'range': self.mon, 'x': 0},
            {'range': self.mon, 'px': 0},
            {'range': self.mon, 'y': 0},
            {'range': self.mon, 'py': 0},
            # TODO: also set betx, bety unchanged?
        ]
        self.madx.match(
            sequence=self.segment.sequence.name,
            vary=steerer_names,
            constraints=constraints,
            twiss_init=self.utool.dict_strip_unit(self.init_twiss))
        self.segment.hook.update()

        # save kicker corrections
        self.steerer_corrections = [
            (el, el.mad_backend.get())
            for el in steerer_elems
        ]

        # show corrections in list box
        self.steerer_corrections_rows = [
            (el.dvm_params[k], v)
            for el, vals in self.steerer_corrections
            for k, v in el.mad2dvm(vals).items()
        ]
        # TODO: update control

        # restore MAD-X values
        for el, val in zip(steerer_elems, steerer_values):
            el.mad_backend.set(val)
