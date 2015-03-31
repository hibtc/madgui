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
from cpymad.model import Locator, Model as CPModel

# internal
from madgui.core import wx
from madgui.component.lineview import TwissView
from madgui.util.common import cachedproperty
from madgui.widget.input import Widget, ShowModal

# exported symbols
__all__ = [
    'OpenModelWidget',
]


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

    def get_definition(self, model):
        """Return a model definition for the model name."""
        return self._locator.get_definition(model)

    def get_repository(self, definition):
        return self._locator.get_repository(definition)

    @classmethod
    def discover(cls):
        """Return list of all locators at the entrypoint madgui.models."""
        return [cls(ep.name, ep.load()())
                for ep in iter_entry_points('madgui.models')]

    @classmethod
    def from_pkg(cls, pkg_name):
        """List all models in the given package. Returns a Locator."""
        try:
            pkg = import_module(pkg_name)
        except (ValueError, KeyError, ImportError, TypeError):
            # '' => ValueError, 'hit.' => KeyError,
            # 'FOOBAR' => ImportErrow, '.' => TypeError
            return None
        resource_provider = PackageResource(pkg_name)
        return cls(pkg_name, Locator(resource_provider))

    @classmethod
    def from_path(cls, path_name):
        """List all models in the given directory. Returns a Locator."""
        if not os.path.isdir(path_name):
            return None
        resource_provider = FileResource(path_name)
        return cls(path_name, Locator(resource_provider))


class ValueContainer(object):
    pass


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

        results = ValueContainer()

        if cls.ShowModal(frame, results=results) != wx.ID_OK:
            return

        mdata = results.mdata
        repo = results.repo
        optic = results.optic

        if not mdata:
            return

        utool = frame.madx_units
        madx = frame.env['madx']
        cpymad_model = CPModel(data=mdata, repo=repo, madx=madx)
        cpymad_model.optics[optic].init()

        frame.env['model'] = cpymad_model
        frame.env['simulator'].model = cpymad_model

        TwissView.create(frame.env['simulator'], frame, basename='env')

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
        self.ctrl_pkg = self._AddCombo('Package:', wx.CB_DROPDOWN|wx.CB_SORT)
        self.ctrl_model = self._AddCombo('Model:', wx.CB_READONLY|wx.CB_SORT)
        self.ctrl_optic = self._AddCombo('Optic:', wx.CB_READONLY|wx.CB_SORT)
        # register for events
        self.Window.Bind(wx.EVT_TEXT, self.OnPackageChange, self.ctrl_pkg)
        self.Window.Bind(wx.EVT_COMBOBOX, self.OnPackageChange, self.ctrl_pkg)
        self.Window.Bind(wx.EVT_COMBOBOX, self.OnModelChange, self.ctrl_model)
        return controls

    def OnPackageChange(self, event):
        """Update model list when package name is changed."""
        ctrl = self.ctrl_pkg
        sel = ctrl.GetSelection()
        val = ctrl.GetValue()
        if sel == wx.NOT_FOUND and val in self.locator_names:
            ctrl.SetStringSelection(val)
        self.UpdateModelList()

    def OnModelChange(self, event):
        """Update optic list when the model selection has changed."""
        self.UpdateOpticList()

    def GetCurrentLocator(self):
        """Get the currently selected locator."""
        selection = self.ctrl_pkg.GetSelection()
        if selection == wx.NOT_FOUND:
            source = self.ctrl_pkg.GetValue()
            return (CachedLocator.from_pkg(source) or
                    CachedLocator.from_path(source))
        else:
            return self.locators[selection]

    def GetCurrentModelDefinition(self):
        """Get the model definition data for the currently selected model."""
        locator = self.GetCurrentLocator()
        model = self.ctrl_model.GetValue()
        return locator.get_definition(model)

    def GetModelList(self):
        """Get list of models in the package specified by the input field."""
        locator = self.GetCurrentLocator()
        return list(locator.list_models()) if locator else []

    def UpdateLocatorList(self):
        """Update the list of locators shown in the dialog."""
        self.locators = CachedLocator.discover()
        # Format entrypoint names, so they can't be confused with package
        # names. This can be used in the EVT_TEXT handler to decide whether
        # to use the entrypoint or package:
        self.locator_names = [u'<{}>'.format(l.name) for l in self.locators]
        self.ctrl_pkg.SetItems(self.locator_names)
        self.ctrl_pkg.SetSelection(0)
        self.ctrl_pkg.Enable(bool(self.locators))

    def UpdateModelList(self):
        """Update displayed model list."""
        modellist = self.GetModelList()
        self.ctrl_model.SetItems(modellist)
        self.ctrl_model.SetSelection(0)
        self.ctrl_model.Enable(bool(modellist))

    def UpdateOpticList(self):
        """Update list of optics."""
        mdef = self.GetCurrentModelDefinition()
        optics = mdef['optics']
        self.ctrl_optic.SetItems(list(optics))
        self.ctrl_optic.SetStringSelection(mdef['default-optic'])
        self.ctrl_optic.Enable(bool(optics))

    def TransferFromWindow(self):
        """Get selected package and model name."""
        locator = self.GetCurrentLocator()
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
        self.UpdateOpticList()

    def Validate(self, parent):
        """Update the status of the OK button."""
        return bool(self.GetModelList())
