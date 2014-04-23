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
from madgui.util.common import cachedproperty

# TODO: select sequence, optic, range


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


class OpenModelDlg(wx.Dialog):

    """
    Open dialog for models contained in python packages.
    """

    @classmethod
    def connect_menu(cls, frame, menubar):
        def OnOpenModel(event):
            dlg = cls(frame)
            if dlg.ShowModal() == wx.ID_OK:
                _frame = frame.Reserve(madx=dlg.model.madx,
                                       control=dlg.model,
                                       model=dlg.model.model)
                dlg.model.hook.show(dlg.model, _frame)
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
        # TODO: redirect history+output to frame!
        cpymad_model = cpymad.model(mdata, histfile=None)
        cpymad_model.twiss()
        seqname = cpymad_model._active['sequence']
        seqobj = cpymad_model._madx.get_sequence(seqname)
        self.model = Model(cpymad_model._madx,
                           name=seqname,
                           twiss_args=cpymad_model._get_twiss_initial(),
                           elements=seqobj.get_elements(),
                           model=cpymad_model)

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
