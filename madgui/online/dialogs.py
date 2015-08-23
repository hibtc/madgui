"""
Dialog for selecting DVM parameters to be synchronized.
"""

from __future__ import absolute_import

from functools import partial

from madgui.core import wx
from madgui.widget.listview import ListCtrl, ColumnInfo
from madgui.widget.input import Widget
from madgui.widget.element import ElementWidget
from madgui.widget import wizard
from madgui.util.unit import format_quantity, tounit



def el_names(elems):
    return [el['name'] for el in elems]


def set_value(ctrl, text):
    if ctrl.GetValue() != text:
        ctrl.SetValue(text)


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


class OVM_Step(Widget):

    def CreateControls(self, window):
        sizer = wx.BoxSizer(wx.HORIZONTAL)

        def box(title, label1, label2, style):
            vsizer = wx.BoxSizer(wx.VERTICAL)
            bsizer = wx.FlexGridSizer(cols=3)

            ctrl_title = wx.StaticText(window, label=title)
            ctrl_label1 = wx.StaticText(window, label=label1)
            ctrl_label2 = wx.StaticText(window, label=label2)
            ctrl_input1 = wx.TextCtrl(window, style=style)
            ctrl_input2 = wx.TextCtrl(window, style=style)

            bsizer.Add(ctrl_label1,
                       flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL,
                       border=5)
            bsizer.AddSpacer(10)
            bsizer.Add(ctrl_input1,
                       flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL,
                       border=5)
            bsizer.Add(ctrl_label2,
                       flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL,
                       border=5)
            bsizer.AddSpacer(10)
            bsizer.Add(ctrl_input2,
                       flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL,
                       border=5)

            vsizer.Add(ctrl_title,
                       flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL,
                       border=5)
            vsizer.Add(bsizer, flag=wx.ALL|wx.ALIGN_LEFT|wx.EXPAND,
                       border=5)

            sizer.Add(vsizer, flag=wx.ALL|wx.EXPAND|wx.ALIGN_TOP, border=5)

            return ctrl_input1, ctrl_input2

        self.edit_qp = box("Enter QP settings:", "QP 1:", "QP 2:",
                           wx.TE_RIGHT)

        sizer.AddSpacer(5)
        button_apply = wx.Button(window, label=">>", style=wx.BU_EXACTFIT)
        sizer.Add(button_apply, flag=wx.ALL|wx.ALIGN_CENTER, border=5)
        sizer.AddSpacer(5)

        self.disp_qp = box("Current QP settings:", "QP 1:", "QP 2:",
                           wx.TE_RIGHT|wx.TE_READONLY)

        sizer.AddSpacer(5)
        line = wx.StaticLine(window, style=wx.LI_VERTICAL)
        sizer.Add(line, flag=wx.ALL|wx.EXPAND, border=5)
        sizer.AddSpacer(5)

        self.disp_mon = box("Monitor readout:", "x:", "y:",
                            wx.TE_RIGHT|wx.TE_READONLY)

        button_apply.Bind(wx.EVT_BUTTON, self.OnApply)

        self.timer = wx.Timer(self.Window)
        window.Bind(wx.EVT_TIMER, self.UpdateStatus, self.timer)

        return sizer

    def GetData(self):
        pass

    def SetData(self, ovm):
        self.ovm = ovm
        # TODO: show full parameter names
        # TODO: show units for KL!
        self.UpdateStatus()
        self.timer.Start(100)

    def OnApply(self, event):
        self._SetQP(0)
        self._SetQP(1)
        self.ovm.control._plugin.execute()

    def _SetQP(self, index):
        qp_elem = self.ovm.get_qp(index)
        qp_value = float(self.edit_qp[index].GetValue())
        qp_value = self.ovm.utool.add_unit('kL', qp_value)
        values = {'kL': qp_value}
        qp_elem.mad_backend.set(qp_elem.mad_converter.to_backend(values))
        qp_elem.dvm_backend.set(qp_elem.dvm_converter.to_backend(values))

    def UpdateStatus(self, event=None):
        self.UpdateBeam()
        self.UpdateQPs()

    def UpdateBeam(self):
        data = self.ovm.get_monitor().dvm_backend.get()
        set_value(self.disp_mon[0], format_quantity(data['posx']))
        set_value(self.disp_mon[1], format_quantity(data['posy']))

    def UpdateQPs(self):
        self._UpdateQP(0)
        self._UpdateQP(1)

    def _UpdateQP(self, index):
        data = self.ovm.get_qp(index).dvm_backend.get()
        set_value(self.disp_qp[index], format_quantity(data['kL']))


class OVM_Summary(Widget):

    def CreateControls(self, window):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        def box(title, columns):
            label = wx.StaticText(window, label=title)
            lctrl = ListCtrl(window, columns, style=wx.LC_NO_HEADER)
            lctrl.SetMinSize(wx.Size(250, 150))
            vsizer = wx.BoxSizer(wx.VERTICAL)
            vsizer.Add(label, flag=wx.ALL|wx.ALIGN_TOP, border=5)
            vsizer.Add(lctrl, 1, flag=wx.ALL|wx.EXPAND, border=5)
            sizer.Add(vsizer, 1, flag=wx.ALL|wx.EXPAND, border=5)
            return lctrl
        self.twiss_init = box("Initial position:", self.GetTwissCols())
        self.steerer_corr = box("Steerer corrections:", self.GetSteererCols())
        return sizer

    # TODO: restart button

    def GetData(self):
        pass

    def SetData(self, ovm):
        self.ovm = ovm

    def Update(self):
        pos = self.ovm.compute_initial_position()
        self.steerer_corrections = self.ovm.compute_steerer_corrections(pos)
        steerer_corrections_rows = [
            (el.dvm_params[k], v)
            for el, vals in self.steerer_corrections
            for k, v in el.mad2dvm(vals).items()
        ]
        self.twiss_init.items = sorted(pos.items(), key=lambda item: item[0])
        self.steerer_corr.items = steerer_corrections_rows

    def GetTwissCols(self):
        return [
            ColumnInfo(
                "Param",
                lambda index, item: item[0],
                wx.LIST_FORMAT_LEFT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "Value",
                lambda index, item: format_quantity(item[1]),
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
        ]

    def GetSteererCols(self):
        return [
            ColumnInfo(
                "Param",
                self._format_param,
                wx.LIST_FORMAT_LEFT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "Value",
                self._format_dvm_value,
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
        ]

    def _format_param(self, index, item):
        param, val = item
        return param.name

    def _format_dvm_value(self, index, item):
        param, val = item
        return format_dvm_value(param, val)


class OpticVariationWizard(wizard.Wizard):

    def __init__(self, parent, ovm):
        super(OpticVariationWizard, self).__init__(parent)
        self.ovm = ovm
        self._add_step_page("1st optic")
        self._add_step_page("2nd optic")
        self._add_confirm_page()

    def _add_step_page(self, title):
        page = self.AddPage(title)
        widget = OVM_Step(page.canvas)
        widget.SetData(self.ovm)

    def _add_confirm_page(self):
        page = self.AddPage("Confirm steerer corrections")
        widget = OVM_Summary(page.canvas)
        widget.SetData(self.ovm)
        self.summary = widget

    def NextPage(self):
        if self.cur_page in (0, 1):
            self.ovm.record_measurement(self.cur_page)
        super(OpticVariationWizard, self).NextPage()
        if self.cur_page == 2:
            self.summary.Update()

    def OnFinishButton(self, event):
        for el, vals in self.summary.steerer_corrections:
            el.mad_backend.set(vals)
            el.dvm_backend.set(el.mad2dvm(vals))
        self.ovm.control._plugin.execute()
