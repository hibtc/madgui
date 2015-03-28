# encoding: utf-8
"""
Widget component to find/open a model.
"""

# force new style imports
from __future__ import absolute_import

# standard library
from importlib import import_module
from pkg_resources import iter_entry_points

# 3rd party
from cpymad.resource.package import PackageResource
from cpymad.model import Locator, Model as CPModel

# internal
from madgui.core import wx
from madgui.component.lineview import TwissView
from madgui.util.common import cachedproperty
from madgui.widget.input import Widget

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
        except ValueError:
            return None
        except ImportError:
            return None
        resource_provider = PackageResource(pkg_name)
        return cls(pkg_name, Locator(resource_provider))


class ValueContainer(object):
    pass


class OpenModelWidget(Widget):

    """
    Open dialog for models contained in python packages.
    """

    title = "select model"

    @classmethod
    def create(cls, frame):
        # select package, model:

        results = ValueContainer()

        if cls.ShowModal(frame, results=results) != wx.ID_OK:
            return

        mdata = results.mdata
        repo = results.repo

        if not mdata:
            return

        # TODO: model selection belongs into a separate function, that is
        # called here (hook?) and can be selected from a menu element as well.

        # select optic, sequence, beam, range, twiss:
        title = "Select model configuration"

        # Create a temporary model for convenience:
        cpymad_model = CPModel(data=mdata, repo=repo, madx=None)
        optics = list(cpymad_model.optics)
        select_detail_dlg = wx.SingleChoiceDialog(
            frame,
            'Select optic:',
            'Select optic',
            optics)
        select_detail_dlg.SetSelection(
            optics.index(cpymad_model.default_optic.name))
        try:
            if select_detail_dlg.ShowModal() != wx.ID_OK:
                return
            optic = select_detail_dlg.GetStringSelection()
        finally:
            select_detail_dlg.Destroy()
        # TODO: redirect history+output to frame!
        madx = frame.env['madx']
        cpymad_model = CPModel(data=mdata, repo=repo, madx=madx)
        cpymad_model.optics[optic].init()

        utool = frame.madx_units

        # TODO: forward range/sequence to Model
        # range is currently not used at all
        frame.env['model'] = cpymad_model
        frame.env['simulator'].model = cpymad_model

        TwissView.create(frame.env['simulator'], frame, basename='env')

    def CreateControls(self):

        """Create subcontrols and layout."""

        window = self.GetWindow()

        # Create controls
        label_pkg = wx.StaticText(window, label="Package:")
        label_model = wx.StaticText(window, label="Model:")
        self.ctrl_pkg = wx.ComboBox(window, wx.CB_DROPDOWN|wx.CB_SORT)
        self.ctrl_model = wx.ComboBox(window, wx.CB_READONLY|wx.CB_SORT)

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

        # register for events
        window.Bind(wx.EVT_TEXT, self.OnPackageChange, source=self.ctrl_pkg)

        return controls

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
        return True

    def TransferToWindow(self):
        """Update displayed package and model name."""
        self.UpdateLocatorList()
        self.UpdateModelList()
        # self.ctrl_pkg.SetValue(self.data.pkg_name)
        # self.ctrl_model.SetValue(self.data.model_name)
        return True

    def Validate(self, parent):
        """Update the status of the OK button."""
        return bool(self.GetModelList())
