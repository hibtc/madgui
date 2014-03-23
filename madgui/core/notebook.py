# encoding: utf-8
"""
Notebook window component for MadGUI (main window).
"""

# force new style imports
from __future__ import absolute_import

# GUI components
import wx
import wx.aui
from wx.py.crust import Crust

# internal
from madgui.util.common import ivar
from madgui.util.plugin import HookCollection
from madgui.core.figure import FigurePanel

# exported symbols
__all__ = ['NotebookFrame']


class NotebookFrame(wx.Frame):

    """
    Notebook window class for MadGUI (main window).
    """

    hook = ivar(HookCollection,
                init='madgui.core.notebook.init',
                menu='madgui.core.notebook.menu')

    def __init__(self, app, show=True):

        """
        Create notebook frame.

        Extends wx.Frame.__init__.
        """

        super(NotebookFrame, self).__init__(
            parent=None,
            title='MadGUI',
            size=wx.Size(800, 600))

        self.logfolder = app.logfolder

        # create notebook
        self.panel = wx.Panel(self)
        self.notebook = wx.aui.AuiNotebook(self.panel)
        sizer = wx.BoxSizer()
        sizer.Add(self.notebook, 1, wx.EXPAND)
        self.panel.SetSizer(sizer)
        self.notebook.Bind(
            wx.aui.EVT_AUINOTEBOOK_PAGE_CLOSED,
            self.OnPageClosed,
            source=self.notebook)

        # create menubar and listen to events:
        self.SetMenuBar(self._CreateMenu())

        # Create a command tab
        self.NewCommandTab()

        # show the frame
        self.Show(show)

    def _CreateMenu(self):
        """Create a menubar."""
        # TODO: this needs to be done more dynamically. E.g. use resource
        # files and/or a plugin system to add/enable/disable menu elements.
        menubar = wx.MenuBar()
        appmenu = wx.Menu()
        menubar.Append(appmenu, '&App')
        # Create menu items
        shellitem = appmenu.Append(wx.ID_ANY,
                                   '&New prompt\tCtrl+N',
                                   'Open a new tab with a command prompt')
        self.Bind(wx.EVT_MENU, self.OnNewShell, shellitem)
        self.hook.menu(self, menubar)
        appmenu.AppendSeparator()
        appmenu.Append(wx.ID_EXIT, '&Quit', 'Quit application')
        self.Bind(wx.EVT_MENU, self.OnQuit, id=wx.ID_EXIT)
        return menubar

    def AddView(self, view, title):
        """Add new notebook tab for the view."""
        # TODO: remove this method in favor of a event based approach?
        panel = FigurePanel(self.notebook, view)
        self.notebook.AddPage(panel, title, select=True)
        view.plot()
        return panel

    def OnPageClosed(self, event):
        """A page has been closed. If it was the last, close the frame."""
        if self.notebook.GetPageCount() == 0:
            self.Close()

    def OnQuit(self, event):
        """Close the window."""
        self.Close()

    def OnNewShell(self, event):
        """Open a new command tab."""
        self.NewCommandTab()

    def NewCommandTab(self):
        """Open a new command tab."""
        # TODO: create a toolbar for this tab as well
        # TODO: prevent the first command tab from being closed (?)
        # TODO: redirect output?
        self.notebook.AddPage(Crust(self.notebook), "Command", select=True)
