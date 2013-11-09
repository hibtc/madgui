"""
Contains opendialog for models.
"""
from importlib import import_module
from collections import namedtuple

from cern.resource.package import PackageResource
from cern.cpymad.model_locator import MergedModelLocator

import wx


def list_models(pkg_name):
    """List all models in the given package. Returns an iteratable."""
    try:
        pkg = import_module(pkg_name)
    except ValueError:
        return None
    except ImportError:
        return None
    resource_provider = PackageResource(pkg_name)
    model_locator = MergedModelLocator(resource_provider)
    return model_locator.list_models()


PackageModel = namedtuple('PackageModel', ['pkg_name', 'model_name'])

class OpenModelDlg(wx.Dialog):
    """
    Open dialog for models contained in python packages.

    Displays

    """
    def __init__(self, *args, **kwargs):
        """
        Store the data and initialize the component.

        :param PackageModel data: default package and model names.

        """
        self.data = PackageModel("hit_models", "hht3")
        super(OpenModelDlg, self).__init__(*args, **kwargs)
        self.CreateControls()
        self.Centre()

    def CreateControls(self):
        """Create subcontrols and layout."""
        # Create controls
        label_pkg = wx.StaticText(self, label="Package:")
        label_model = wx.StaticText(self, label="Model:")
        self.ctrl_pkg = wx.TextCtrl(self)
        self.ctrl_model = wx.ComboBox(self, wx.CB_DROPDOWN|wx.wx.CB_READONLY|wx.CB_SORT)

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
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        button_ok = wx.Button(self, wx.ID_OK)
        button_cancel = wx.Button(self, wx.ID_CANCEL)
        buttons.Add(button_ok)
        buttons.Add(button_cancel)

        # outer layout sizer
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(controls, flag=wx.ALIGN_CENTER_VERTICAL|wx.EXPAND|wx.ALL, **sizeargs)
        outer.Add(buttons, flag=wx.ALIGN_CENTER_HORIZONTAL|wx.ALL, **sizeargs)

        # register for events
        self.Bind(wx.EVT_TEXT, self.OnPackageChange, source=self.ctrl_pkg)
        self.Bind(wx.EVT_BUTTON, self.OnButtonOk, source=button_ok)
        self.Bind(wx.EVT_BUTTON, self.OnButtonCancel, source=button_cancel)
        self.Bind(wx.EVT_UPDATE_UI, self.UpdateButtonOk, source=button_ok)

        # associate sizer and layout
        self.SetSizer(outer)
        outer.Fit(self)


    def OnPackageChange(self, event):
        """Update model list when package name is changed."""
        self.UpdateModelList()

    def GetModelList(self):
        """Get list of models in the package specified by the input field."""
        pkg_name = self.ctrl_pkg.GetValue()
        modellist = list_models(pkg_name)
        return [] if modellist is None else list(modellist)

    def UpdateModelList(self):
        """Update displayed model list."""
        modellist = self.GetModelList()
        self.ctrl_model.SetItems(modellist)
        self.ctrl_model.Enable(bool(modellist))

    # TODO: Use validators:
    # - Check the validity of the package/model name
    # - disable Ok button
    def TransferDataFromWindow(self):
        """Get selected package and model name."""
        self.data = PackageModel(
            pkg_name=self.ctrl_pkg.GetValue(),
            model_name=self.ctrl_model.GetValue())

    def TransferDataToWindow(self):
        """Update displayed package and model name."""
        self.ctrl_pkg.SetValue(self.data.pkg_name)
        self.UpdateModelList()
        self.ctrl_model.SetValue(self.data.model_name)

    def UpdateButtonOk(self, event):
        modellist = self.GetModelList()
        event.Enable(bool(modellist))

    def OnButtonOk(self, event):
        self.TransferDataFromWindow()
        self.EndModal(wx.ID_OK)

    def OnButtonCancel(self, event):
        self.EndModal(wx.ID_CANCEL)

