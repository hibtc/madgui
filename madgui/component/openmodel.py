# encoding: utf-8
"""
Widget component to find/open a model.
"""

# force new style imports
from __future__ import absolute_import

# standard library
import os
from importlib import import_module
from pkg_resources import iter_entry_points

# 3rd party
from cpymad.resource.file import FileResource
from cpymad.resource.package import PackageResource
from cpymad.model import Locator as _Locator

# internal
from madgui.core import wx
from madgui.util.common import cachedproperty
from madgui.widget.input import Widget, ShowModal

# exported symbols
__all__ = [
    'OpenModelWidget',
]


class Locator(_Locator):

    @classmethod
    def from_pkg(cls, pkg_name):
        """Returns a Locator that lists all models in the given package."""
        try:
            pkg = import_module(pkg_name)
        except (ValueError, KeyError, ImportError, TypeError):
            # '' => ValueError, 'hit.' => KeyError,
            # 'FOOBAR' => ImportErrow, '.' => TypeError
            return None
        return cls(PackageResource(pkg_name))

    @classmethod
    def from_path(cls, path_name):
        """Returns a Locator that lists all models in the given directory."""
        if not os.path.isdir(path_name):
            return None
        return cls(FileResource(path_name))


class OpenModelWidget(Widget):

    """
    Open dialog for models contained in python packages.
    """

    title = "select model"

    def __init__(self, results):
        self.results = results

    @classmethod
    def create(cls, frame):
        # select package, model:
        if cls.ShowModal(frame, results=results) != wx.ID_OK:
            return None
        if not mdata:
            return None
        return cpymad_model

    def _AddCombo(self, label, combo_style):
        """Add a label + combobox to the tabular sizer."""
        ctrl_text = wx.StaticText(self.Window, label=label)
        ctrl_combo = wx.ComboBox(self.Window, combo_style)
        flag = wx.ALL|wx.ALIGN_CENTER_VERTICAL
        self.sizer.Add(ctrl_text, flag=flag|wx.ALIGN_LEFT, border=5)
        self.sizer.Add(ctrl_combo, flag=flag|wx.EXPAND, border=5)
        return ctrl_combo

    def CreateControls(self):
        """Create subcontrols and layout."""
        # Create box sizer
        controls = wx.FlexGridSizer(rows=3, cols=2)
        controls.SetFlexibleDirection(wx.HORIZONTAL)
        controls.AddGrowableCol(1, 1)
        controls.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_ALL)
        self.sizer = controls
        # Create controls
        self.ctrl_pkg = self._AddCombo('Source:', wx.CB_DROPDOWN|wx.CB_SORT)
        self.ctrl_model = self._AddCombo('Model:', wx.CB_READONLY|wx.CB_SORT)
        self.ctrl_optic = self._AddCombo('Optic:', wx.CB_READONLY|wx.CB_SORT)
        # register for events
        self.Window.Bind(wx.EVT_TEXT, self.OnPackageChange, self.ctrl_pkg)
        self.Window.Bind(wx.EVT_COMBOBOX, self.OnPackageChange, self.ctrl_pkg)
        self.Window.Bind(wx.EVT_COMBOBOX, self.OnModelChange, self.ctrl_model)
        self.ctrl_pkg.SetMinSize(wx.Size(200, -1))
        return controls

    def OnPackageChange(self, event):
        """Update model list when package name is changed."""
        ctrl = self.ctrl_pkg
        sel = ctrl.GetSelection()
        val = ctrl.GetValue()
        if sel == wx.NOT_FOUND and val in self.locators:
            ctrl.SetStringSelection(val)
        self.UpdateModelList()

    def OnModelChange(self, event):
        """Update optic list when the model selection has changed."""
        self.UpdateOpticList()

    def GetCurrentLocator(self):
        """Get the currently selected locator."""
        ctrl = self.ctrl_pkg
        if ctrl.GetSelection() == wx.NOT_FOUND:
            source = ctrl.GetValue()
            return (Locator.from_pkg(source) or
                    Locator.from_path(source))
        else:
            return self.locators[ctrl.GetStringSelection()]()

    def GetModelList(self):
        """Get list of models in the package specified by the input field."""
        return list(self.locator.list_models()) if self.locator else []

    def GetOpticList(self):
        """Get the model definition data for the currently selected model."""
        if not self.locator or not self.modellist:
            return [], ''
        model = self.ctrl_model.GetValue()
        mdef = self.locator.get_definition(model)
        return list(mdef.get('optics', {})), mdef.get('default-optic', '')

    def UpdateLocatorList(self):
        """Update the list of locators shown in the dialog."""
        # Note that entrypoints are lazy-loaded:
        self.locators = {u'<{}>'.format(ep.name): lambda: ep.load()()
                         for ep in iter_entry_points('madgui.models')}
        # Format entrypoint names, so they can't be confused with package
        # names. This can be used in the EVT_TEXT handler to decide whether
        # to use the entrypoint or package:
        self.ctrl_pkg.SetItems(list(self.locators))
        self.ctrl_pkg.SetSelection(0)
        self.ctrl_pkg.Enable(bool(self.locators))

    def UpdateModelList(self):
        """Update displayed model list."""
        # UpdateModelList is called on initialization and each time the
        # 'source' field changes. So this is the place to update the current
        # locator. Note that is a deliberate choice not to cache anything
        # located, so files can be changed before applying the dialog:
        self.locator = self.GetCurrentLocator()
        self.modellist = self.GetModelList()
        self.ctrl_model.SetItems(self.modellist)
        self.ctrl_model.SetSelection(0)
        self.ctrl_model.Enable(bool(self.modellist))
        self.UpdateOpticList()

    def UpdateOpticList(self):
        """Update list of optics."""
        optics, selected = self.GetOpticList()
        self.ctrl_optic.SetItems(optics)
        self.ctrl_optic.SetStringSelection(selected)
        self.ctrl_optic.Enable(bool(optics))

    def TransferFromWindow(self):
        """Get selected package and model name."""
        locator = self.locator
        if locator:
            mdata = locator.get_definition(self.ctrl_model.GetValue())
            repo = locator.get_repository(mdata)
        else:
            mdata = None
            repo = None
        self.results.mdata = mdata
        self.results.repo = repo
        self.results.optic = self.ctrl_optic.GetValue()

    def TransferToWindow(self):
        """Update displayed package and model name."""
        self.UpdateLocatorList()
        self.UpdateModelList()

    def Validate(self, parent):
        """Update the status of the OK button."""
        return bool(self.modellist)
