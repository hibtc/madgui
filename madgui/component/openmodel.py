# encoding: utf-8
"""
Dialog component to find/open a model.
"""

# force new style imports
from __future__ import absolute_import

# standard library
from importlib import import_module
from pkg_resources import iter_entry_points

# 3rd party
from cern.resource.package import PackageResource
from cern.cpymad.model_locator import MergedModelLocator
from cern import cpymad

# internal
from madgui.core import wx
from madgui.component.model import Model
from madgui.component.modeldetail import ModelDetailDlg
from madgui.util.common import cachedproperty
from madgui.widget.input import ModalDialog


class CachedLocator(object):

    """
    Cached Model locator.
    """

    def __init__(self, name, locator):
        """Store the name and raw (uncached) locator."""
        self.name = name
        self._locator = locator

    @cachedproperty
    def models(self):
        """Cached list of model names."""
        return list(self._locator.list_models())

    def list_models(self):
        """Return list of model names."""
        return self.models

    def get_model(self, model):
        """Return a ModelData for the model name."""
        return self._locator.get_model(model)

    @classmethod
    def discover(cls):
        """Return list of all locators at the entrypoint madgui.models."""
        return [cls(ep.name, ep.load())
                for ep in iter_entry_points('madgui.models')]

    @classmethod
    def from_pkg(cls, pkg_name):
        """List all models in the given package. Returns a Locator."""
        try:
            pkg = import_module(pkg_name)
        except ValueError:
            return None
        except ImportError:
            return None
        resource_provider = PackageResource(pkg_name)
        return cls(pkg_name, MergedModelLocator(resource_provider))


class OpenModelDlg(ModalDialog):

    """
    Open dialog for models contained in python packages.
    """

    @classmethod
    def connect_menu(cls, frame, menubar):
        def OnOpenModel(event):
            # select package, model:
            select_model_dlg = cls(frame, title="Select model")
            try:
                if select_model_dlg.ShowModal() != wx.ID_OK:
                    return
                mdata = select_model_dlg.mdata
                if not mdata:
                    return
                # select optic, sequence, beam, range, twiss:
                title = "Select model configuration"
                select_detail_dlg = ModelDetailDlg(frame, mdef=mdata.model,
                                                   title=title)
                try:
                    if select_detail_dlg.ShowModal() != wx.ID_OK:
                        return
                    detail = select_detail_dlg.data
                    # TODO: redirect history+output to frame!
                    _frame = frame.Claim()
                    madx = _frame.vars['madx']
                    cpymad_model = cpymad.model.Model(
                        mdata,
                        optics=[detail['optic']],
                        sequence=detail['sequence'],
                        histfile=None,
                        madx=madx)

                    beam = cpymad_model.get_beam(detail['beam'])
                    cpymad_model.set_beam(beam)
                    cpymad_model.set_range(detail['range'])
                    utool = _frame.madx_units
                    twiss_args = cpymad_model._get_twiss_initial(
                        detail['sequence'],
                        detail['range'],
                        detail['twiss'])
                    model = Model(madx,
                                  utool=utool,
                                  name=detail['sequence'],
                                  twiss_args=utool.dict_add_unit(twiss_args),
                                  model=cpymad_model)
                    model.twiss()
                    _frame.vars.update(control=model,
                                       model=cpymad_model)
                    model.hook.show(model, _frame)
                finally:
                    select_detail_dlg.Destroy()
            finally:
                select_model_dlg.Destroy()
        appmenu = menubar.Menus[0][0]
        menuitem = appmenu.Append(wx.ID_ANY, '&Open model\tCtrl+O')
        def OnUpdate(event):
            if frame.IsClaimed():
                menuitem.SetHelp('Open a model in a new frame.')
            else:
                menuitem.SetHelp('Open a model in this frame.')
            # skip the event, so more UpdateUI handlers can be invoked:
            event.Skip()
        frame.Bind(wx.EVT_MENU, OnOpenModel, menuitem)
        frame.Bind(wx.EVT_UPDATE_UI, OnUpdate, menubar)

    def SetData(self):
        """Store the data and initialize the component."""
        self.mdata = None

    def CreateControls(self):

        """Create subcontrols and layout."""

        # Create controls
        label_pkg = wx.StaticText(self, label="Package:")
        label_model = wx.StaticText(self, label="Model:")
        self.ctrl_pkg = wx.ComboBox(self, wx.CB_DROPDOWN|wx.CB_SORT)
        self.ctrl_model = wx.ComboBox(self, wx.CB_READONLY|wx.CB_SORT)
        self.TransferDataToWindow() # needed?

        # Create box sizer
        controls = wx.FlexGridSizer(rows=2, cols=2)
        controls.SetFlexibleDirection(wx.HORIZONTAL)
        controls.AddGrowableCol(1, 1)
        controls.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_ALL)

        # insert items
        left = wx.ALL|wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL
        expand = wx.ALL|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL
        sizeargs = dict(border=5)
        controls.Add(label_pkg, flag=left, **sizeargs)
        controls.Add(self.ctrl_pkg, flag=expand, **sizeargs)
        controls.Add(label_model, flag=left, **sizeargs)
        controls.Add(self.ctrl_model, flag=expand, **sizeargs)

        # buttons
        buttons = self.CreateButtonSizer()

        # outer layout sizer
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(controls, flag=wx.ALIGN_CENTER_VERTICAL|wx.EXPAND|wx.ALL, **sizeargs)
        outer.Add(buttons, flag=wx.ALIGN_CENTER_HORIZONTAL|wx.ALL, **sizeargs)

        # register for events
        self.Bind(wx.EVT_TEXT, self.OnPackageChange, source=self.ctrl_pkg)

        # associate sizer and layout
        self.SetSizer(outer)

    def OnPackageChange(self, event):
        """Update model list when package name is changed."""
        self.UpdateModelList()

    def GetCurrentLocator(self):
        """Get the currently selected locator."""
        selection = self.ctrl_pkg.GetSelection()
        if selection == wx.NOT_FOUND:
            return CachedLocator.from_pkg(self.ctrl_pkg.GetValue())
        else:
            return self.locators[selection]

    def GetModelList(self):
        """Get list of models in the package specified by the input field."""
        locator = self.GetCurrentLocator()
        return list(locator.list_models()) if locator else []

    def UpdateLocatorList(self):
        """Update the list of locators shown in the dialog."""
        self.locators = CachedLocator.discover()
        self.ctrl_pkg.SetItems([l.name for l in self.locators])
        self.ctrl_pkg.SetSelection(0)
        self.ctrl_pkg.Enable(bool(self.locators))

    def UpdateModelList(self):
        """Update displayed model list."""
        modellist = self.GetModelList()
        self.ctrl_model.SetItems(modellist)
        self.ctrl_model.SetSelection(0)
        self.ctrl_model.Enable(bool(modellist))

    def TransferDataFromWindow(self):
        """Get selected package and model name."""
        locator = self.GetCurrentLocator()
        if not locator:
            self.mdata = None
            return
        self.mdata = locator.get_model(self.ctrl_model.GetValue())

    def TransferDataToWindow(self):
        """Update displayed package and model name."""
        self.UpdateLocatorList()
        self.UpdateModelList()
        # self.ctrl_pkg.SetValue(self.data.pkg_name)
        # self.ctrl_model.SetValue(self.data.model_name)

    def CreateButtonOk(self):
        button = super(OpenModelDlg, self).CreateOkButton()
        self.Bind(wx.EVT_UPDATE_UI, self.UpdateButtonOk, source=button_ok)
        return button

    def UpdateButtonOk(self, event):
        """Update the status of the OK button."""
        modellist = self.GetModelList()
        event.Enable(bool(modellist))
