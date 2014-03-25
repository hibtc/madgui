# encoding: utf-8
"""
Dialog component to find/open a model.
"""

# force new style imports
from __future__ import absolute_import

# standard library
from importlib import import_module
from pkg_resources import iter_entry_points
import os

# 3rd party
from cern.resource.package import PackageResource
from cern.cpymad.model_locator import MergedModelLocator
from cern import cpymad

# internal
from madgui.core import wx
from madgui.component.model import Model


def list_locators():
    """Return list of all locators at the entrypoint madgui.models."""
    return [(ep.name, ep.load()) for ep in iter_entry_points('madgui.models')]


def get_locator(pkg_name):
    """List all models in the given package. Returns an iterable."""
    try:
        pkg = import_module(pkg_name)
    except ValueError:
        return None
    except ImportError:
        return None
    resource_provider = PackageResource(pkg_name)
    return MergedModelLocator(resource_provider)


class OpenModelDlg(wx.Dialog):

    """
    Open dialog for models contained in python packages.
    """

    @classmethod
    def connect_menu(cls, frame, menubar):
        def OnOpenModel(event):
            dlg = cls(frame)
            if dlg.ShowModal() == wx.ID_OK:
                dlg.model.hook.show(dlg.model, frame)
            dlg.Destroy()
        appmenu = menubar.Menus[0][0]
        menuitem = appmenu.Append(wx.ID_ANY,
                                  '&Open model\tCtrl+O',
                                  'Open another model in a new tab')
        menubar.Bind(wx.EVT_MENU, OnOpenModel, menuitem)

    def __init__(self, parent, *args, **kwargs):
        """Store the data and initialize the component."""
        self.model = None
        super(OpenModelDlg, self).__init__(parent, *args, **kwargs)
        self.logfolder = parent.logfolder
        self.CreateControls()
        self.Centre()

    def CreateControls(self):

        """Create subcontrols and layout."""

        # Create controls
        label_pkg = wx.StaticText(self, label="Source:")
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

    def GetCurrentLocator(self):
        """Get the currently selected locator."""
        selection = self.ctrl_pkg.GetSelection()
        if selection == wx.NOT_FOUND:
            return get_locator(self.ctrl_pkg.GetValue())
        else:
            return self.locators[selection][1]

    def GetModelList(self):
        """Get list of models in the package specified by the input field."""
        locator = self.GetCurrentLocator()
        return list(locator.list_models()) if locator else []

    def UpdateLocatorList(self):
        """Update the list of locators shown in the dialog."""
        self.locators = list_locators()
        self.ctrl_pkg.SetItems([l[0] for l in self.locators])
        self.ctrl_pkg.SetSelection(0)
        self.ctrl_pkg.Enable(bool(self.locators))

    def UpdateModelList(self):
        """Update displayed model list."""
        modellist = self.GetModelList()
        self.ctrl_model.SetItems(modellist)
        self.ctrl_model.SetSelection(0)
        self.ctrl_model.Enable(bool(modellist))

    # TODO: Use validators:
    # - Check the validity of the package/model name
    # - disable Ok button
    def TransferDataFromWindow(self):
        """Get selected package and model name."""
        locator = self.GetCurrentLocator()
        if not locator:
            self.model = None
            return
        mdata = locator.get_model(self.ctrl_model.GetValue())
        histfile = os.path.join(self.logfolder, "%s.madx" % mdata.name)
        self.model = Model(cpymad.model(mdata, histfile=histfile))

    def TransferDataToWindow(self):
        """Update displayed package and model name."""
        self.UpdateLocatorList()
        self.UpdateModelList()
        # self.ctrl_pkg.SetValue(self.data.pkg_name)
        # self.ctrl_model.SetValue(self.data.model_name)

    def UpdateButtonOk(self, event):
        """Update the status of the OK button."""
        modellist = self.GetModelList()
        event.Enable(bool(modellist))

    def OnButtonOk(self, event):
        """Confirm current selection and close dialog."""
        self.TransferDataFromWindow()
        self.EndModal(wx.ID_OK)

    def OnButtonCancel(self, event):
        """Cancel the dialog."""
        self.EndModal(wx.ID_CANCEL)
