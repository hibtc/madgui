# encoding: utf-8
"""
Utilities for the optic variation method (Optikvarianzmethode) for beam
alignment.
"""

from __future__ import absolute_import

import numpy

from madgui.core import wx
from madgui.util.unit import format_quantity, strip_unit, get_raw_label
from madgui.widget.input import Widget
from madgui.widget.listview import ListCtrl, ColumnInfo
from madgui.widget import wizard

from .dialogs import format_dvm_value

# TODO: use UI units

__all__ = [
    'OpticSelectWidget',
    'OpticVariationMethod',
    'OpticVariationWizard',
    'OVM_Summary',
    'OVM_Step',
]


def _is_steerer(el):
    return el['type'] == 'sbend' \
        or el['type'] == 'multipole' and (
            el['knl'][0] != 0 or
            el['ksl'][0] != 0)


def el_names(elems):
    return [el['name'] for el in elems]


def _static_box(window, title, orient):
    box = wx.StaticBox(window, wx.ID_ANY, title)
    sizer = wx.StaticBoxSizer(box, orient)
    return window, sizer


def set_value(ctrl, text):
    if ctrl.GetValue() != text:
        ctrl.SetValue(text)


def set_label(ctrl, text):
    if ctrl.GetLabel() != text:
        ctrl.SetLabel(text)


class OpticVariationMethod(object):

    """
    Data for the optic variation method.
    """

    def __init__(self, control, mon, qps, hst, vst):
        self.control = control
        self.mon = mon
        self.qps = qps
        self.hst = hst
        self.vst = vst
        self.utool = control._segment.session.utool
        self.segment = control._segment
        self.sectormap = [None, None]
        self.measurement = [None, None]

    def get_monitor(self):
        return self.control.get_element(self.mon)

    def get_qp(self, index):
        return self.control.get_element(self.qps[index])

    def get_transfer_map(self):
        return self.segment.get_transfer_map(
            self.segment.start,
            self.segment.get_element_info(self.mon))

    def record_measurement(self, index):
        monitor = self.get_monitor()
        self.sectormap[index] = self.get_transfer_map()
        self.measurement[index] = monitor.dvm_converter.to_standard(
            monitor.dvm_backend.get())

    def compute_initial_position(self):
        return self._compute_initial_position(
            self.sectormap[0], self.measurement[0],
            self.sectormap[1], self.measurement[1])

    def compute_steerer_corrections(self, init_pos):

        steerer_names = self.hst + self.vst
        steerer_elems = [self.control.get_element(v) for v in steerer_names]

        # backup  MAD-X values
        steerer_values = [el.mad_backend.get() for el in steerer_elems]

        # compute initial condition
        init_twiss = {}
        init_twiss.update(self.segment.twiss_args)
        init_twiss.update(init_pos)
        self.segment._twiss_args = init_twiss

        # match final conditions
        constraints = [
            {'range': self.mon, 'x': 0},
            {'range': self.mon, 'px': 0},
            {'range': self.mon, 'y': 0},
            {'range': self.mon, 'py': 0},
            # TODO: also set betx, bety unchanged?
        ]
        self.segment.madx.match(
            sequence=self.segment.sequence.name,
            vary=steerer_names,
            constraints=constraints,
            twiss_init=self.utool.dict_strip_unit(init_twiss))
        self.segment.hook.update()

        # save kicker corrections
        steerer_corrections = [
            (el, el.mad_backend.get())
            for el in steerer_elems
        ]

        # restore MAD-X values
        for el, val in zip(steerer_elems, steerer_values):
            el.mad_backend.set(val)

        return steerer_corrections

    def _strip_sd_pair(self, sd_values, prefix='pos'):
        strip_unit = self.utool.strip_unit
        return (strip_unit('x', sd_values[prefix + 'x']),
                strip_unit('y', sd_values[prefix + 'y']))

    def _compute_initial_position(self, A, a, B, b):
        """
        Compute initial beam position from two monitor read-outs at different
        quadrupole settings.

        A, B are the 4D SECTORMAPs from start to the monitor.
        a, b are the 2D measurement vectors (x, y)

        This function solves the linear system:

                Ax = a
                Bx = b

        for the 4D phase space vector x and returns the result as a dict with
        keys 'x', 'px', 'y, 'py'.
        """
        zero = numpy.zeros((2,4))
        eye = numpy.eye(4)
        s = ((0,2), slice(0,4))
        M = numpy.bmat([[A[s], zero],
                        [zero, B[s]],
                        [eye,  -eye]])
        m = (self._strip_sd_pair(a) +
             self._strip_sd_pair(b) +
             (0, 0, 0, 0))
        x = numpy.linalg.lstsq(M, m)[0]
        return self.utool.dict_add_unit({'x': x[0], 'px': x[1],
                                         'y': x[2], 'py': x[3]})


class OpticVariationWizard(wizard.Wizard):


    def __init__(self, parent, ovm):
        super(OpticVariationWizard, self).__init__(parent)
        self.ovm = ovm
        # TODO: also include the OVM element selection page
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

    """
    Page that allows setting an optic and then measuring the MONITOR.
    """

    # TODO: CanForward() -> BeamIsStable()

    def CreateControls(self, window):
        outer = wx.BoxSizer(wx.VERTICAL)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        outer.Add(sizer, 0, flag=wx.EXPAND)

        def box(title, label1, label2, style):
            vsizer = wx.BoxSizer(wx.VERTICAL)
            bsizer = wx.FlexGridSizer(cols=4)

            ctrl_title = wx.StaticText(window, label=title)
            ctrl_label1 = wx.StaticText(window, label=label1)
            ctrl_label2 = wx.StaticText(window, label=label2)
            ctrl_input1 = wx.TextCtrl(window, style=style)
            ctrl_input2 = wx.TextCtrl(window, style=style)
            ctrl_unit1 = wx.StaticText(window)
            ctrl_unit2 = wx.StaticText(window)

            bsizer.Add(ctrl_label1,
                       flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL,
                       border=5)
            bsizer.AddSpacer(10)
            bsizer.Add(ctrl_input1,
                       flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL,
                       border=5)
            bsizer.Add(ctrl_unit1,
                       flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL,
                       border=5)

            bsizer.Add(ctrl_label2,
                       flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL,
                       border=5)
            bsizer.AddSpacer(10)
            bsizer.Add(ctrl_input2,
                       flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL,
                       border=5)
            bsizer.Add(ctrl_unit2,
                       flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL,
                       border=5)

            vsizer.Add(ctrl_title,
                       flag=wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL,
                       border=5)
            vsizer.Add(bsizer, flag=wx.ALL|wx.ALIGN_LEFT|wx.EXPAND,
                       border=5)

            sizer.Add(vsizer, flag=wx.ALL|wx.EXPAND|wx.ALIGN_TOP, border=5)

            return (ctrl_title,
                    (ctrl_label1, ctrl_label2),
                    (ctrl_input1, ctrl_input2),
                    (ctrl_unit1, ctrl_unit2))

        _, self.label_edit_qp, self.edit_qp, self.edit_qp_unit = \
            box("Enter QP settings:", "QP 1:", "QP 2:", wx.TE_RIGHT)

        sizer.AddSpacer(5)
        sep_sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(sep_sizer, flag=wx.EXPAND)
        sizer.AddSpacer(5)

        button_apply = wx.Button(window, label=">>", style=wx.BU_EXACTFIT)
        sep_sizer.Add(wx.StaticLine(window, style=wx.LI_VERTICAL), 1,
                      flag=wx.ALIGN_CENTER)
        sep_sizer.Add(button_apply, flag=wx.ALL|wx.ALIGN_CENTER, border=5)
        sep_sizer.Add(wx.StaticLine(window, style=wx.LI_VERTICAL), 1,
                      flag=wx.ALIGN_CENTER)

        _, self.label_disp_qp, self.disp_qp, self.disp_qp_unit = \
            box("Current QP settings:", "QP 1:", "QP 2:", wx.TE_RIGHT|wx.TE_READONLY)

        sizer.AddSpacer(5)
        line = wx.StaticLine(window, style=wx.LI_VERTICAL)
        sizer.Add(line, flag=wx.ALL|wx.EXPAND, border=5)
        sizer.AddSpacer(5)

        _, _, self.disp_mon, self.disp_mon_unit = \
            box("Monitor readout:", "x:", "y:", wx.TE_RIGHT|wx.TE_READONLY)

        button_apply.Bind(wx.EVT_BUTTON, self.OnApply)

        self.timer = wx.Timer(window)
        window.Bind(wx.EVT_TIMER, self.UpdateStatus, self.timer)

        return outer

    def GetData(self):
        pass

    def SetData(self, ovm):
        self.ovm = ovm
        self.qp_ui_units = [None, None]
        self._InitManualQP(0)
        self._InitManualQP(1)
        self.UpdateStatus()
        self.timer.Start(100)

    def _InitManualQP(self, index):
        qp_elem = self.ovm.get_qp(index)
        param_info = qp_elem.dvm_converter.param_info['kL']
        ui_unit = self.qp_ui_units[index] = param_info.ui_unit
        unit_label = get_raw_label(ui_unit)

        qp_value = qp_elem.dvm_backend.get()['kL']
        self.edit_qp[index].SetValue(self._fmt_kl(qp_value, index))

        param_name = param_info.name
        self.label_edit_qp[index].SetLabel(param_name + ':')
        self.label_disp_qp[index].SetLabel(param_name + ':')
        self.edit_qp_unit[index].SetLabel(unit_label)
        self.disp_qp_unit[index].SetLabel(unit_label)

    def OnApply(self, event):
        self._SetQP(0)
        self._SetQP(1)
        self.ovm.control._plugin.execute()

    def _SetQP(self, index):
        qp_elem = self.ovm.get_qp(index)
        qp_value = float(self.edit_qp[index].GetValue())
        qp_value = qp_value * self.qp_ui_units[index]
        values = {'kL': qp_value}
        qp_elem.mad_backend.set(qp_elem.mad_converter.to_backend(values))
        qp_elem.dvm_backend.set(qp_elem.dvm_converter.to_backend(values))

    def UpdateStatus(self, event=None):
        self.UpdateBeam()
        self.UpdateQPs()

    def UpdateBeam(self):
        data = self.ovm.get_monitor().dvm_backend.get()
        set_value(self.disp_mon[0], '{:5}'.format(data['posx'].magnitude))
        set_value(self.disp_mon[1], '{:5}'.format(data['posy'].magnitude))
        set_label(self.disp_mon_unit[0], get_raw_label(data['posx']))
        set_label(self.disp_mon_unit[1], get_raw_label(data['posy']))

    def UpdateQPs(self):
        self._UpdateQP(0)
        self._UpdateQP(1)

    def _UpdateQP(self, index):
        data = self.ovm.get_qp(index).dvm_backend.get()
        set_value(self.disp_qp[index], self._fmt_kl(data['kL'], index))

    def _fmt_kl(self, value, index):
        return '{:5}'.format(strip_unit(value, self.qp_ui_units[index]))


class OVM_Summary(Widget):

    """
    Final summary + confirm page for the OVM wizard. Shows calculated initial
    position and steerer corrections.
    """

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
        # TODO: add a restart button
        return sizer

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
        """Column description for the calculated initial conditions."""
        return [
            ColumnInfo(
                "Param",
                lambda item: item[0],
                wx.LIST_FORMAT_LEFT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "Value",
                lambda item: format_quantity(item[1]),
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
        ]

    def GetSteererCols(self):
        """Column description for the calculated steerer corrections."""
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

    def _format_param(self, item):
        param, val = item
        return param.name

    def _format_dvm_value(self, item):
        param, val = item
        return format_dvm_value(param, val)
