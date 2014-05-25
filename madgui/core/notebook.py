# encoding: utf-8
"""
Notebook window component for MadGUI (main window).
"""

# force new style imports
from __future__ import absolute_import

# standard library
import logging
import subprocess
import threading

# GUI components
import wx
import wx.aui
from wx.py.crust import Crust

# 3rd party
from cern.cpymad.madx import Madx
from cern.cpymad import _libmadx_rpc

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

        self.app = app
        self._claimed = False
        self.vars = {}

        self.CreateControls()

        service, process = _libmadx_rpc.LibMadxClient.spawn_subprocess(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0)
        threading.Thread(target=self._read_stream,
                         args=(process.stdout,)).start()
        libmadx = service.libmadx
        madx = Madx(libmadx=libmadx)

        self.vars.update({
            'frame': self,
            'views': [],
            'madx': madx,
            'libmadx': libmadx
        })

        # show the frame
        self.Show(show)

    def CreateControls(self):
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
        self.notebook.Bind(
            wx.aui.EVT_AUINOTEBOOK_PAGE_CLOSE,
            self.OnPageClose,
            source=self.notebook)
        self.CreateStatusBar()
        # create menubar and listen to events:
        self.SetMenuBar(self._CreateMenu())
        # Create a command tab
        self._NewCommandTab()
        self._NewLogTab()

    def Claim(self):
        """
        Claim ownership of a frame.

        If this frame is already claimed, returns a new frame. If this frame
        is not claimed, sets the status to claimed and returns self.

        This is used to prevent several models/files to be opened in the
        same frame (using the same Madx instance) with the menu actions.
        """
        if self._claimed:
            return self.__class__(self.app).Claim()
        else:
            self._claimed = True
            return self

    def IsClaimed(self):
        return self._claimed

    def _CreateMenu(self):
        """Create a menubar."""
        # TODO: this needs to be done more dynamically. E.g. use resource
        # files and/or a plugin system to add/enable/disable menu elements.
        menubar = self.menubar = wx.MenuBar()
        appmenu = wx.Menu()
        seqmenu = wx.Menu()
        menubar.Append(appmenu, '&App')
        menubar.Append(seqmenu, '&Sequence')
        # Create menu items
        self.hook.menu(self, menubar)
        appmenu.AppendSeparator()
        appmenu.Append(wx.ID_EXIT, '&Quit', 'Quit application')
        self.Bind(wx.EVT_MENU, self.OnQuit, id=wx.ID_EXIT)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, menubar)
        return menubar

    def AddView(self, view, title):
        """Add new notebook tab for the view."""
        # TODO: remove this method in favor of a event based approach?
        panel = FigurePanel(self.notebook, view)
        self.notebook.AddPage(panel, title, select=True)
        view.plot()
        self.vars['views'].append(view)
        return panel

    def OnPageClose(self, event):
        """Prevent the command tab from closing, if other tabs are open."""
        if event.Selection <= 1 and self.notebook.GetPageCount() > 2:
            event.Veto()

    def OnPageClosed(self, event):
        """A page has been closed. If it was the last, close the frame."""
        if self.notebook.GetPageCount() == 1:
            self.Close()
        else:
            del self.vars['views'][event.Selection - 1]

    def OnQuit(self, event):
        """Close the window."""
        self.Close()

    def OnUpdateMenu(self, event):
        self.menubar.EnableTop(1, 'control' in self.vars)
        event.Skip()

    def _NewCommandTab(self):
        """Open a new command tab."""
        self.notebook.AddPage(
            Crust(self.notebook, locals=self.vars),
            "Command",
            select=True)

    def _NewLogTab(self):
        """Create a tab for logging."""
        panel = wx.Panel(self.notebook, wx.ID_ANY)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)
        textctrl = wx.TextCtrl(panel, wx.ID_ANY,
                               style=wx.TE_MULTILINE|wx.TE_READONLY)
        monospace = wx.Font(10,
                            wx.FONTFAMILY_MODERN,
                            wx.FONTSTYLE_NORMAL,
                            wx.FONTWEIGHT_NORMAL)
        textctrl.SetFont(monospace)
        sizer.Add(textctrl, 1, wx.EXPAND)
        self.notebook.AddPage(panel, "Log", select=False)
        self._log_ctrl = textctrl
        self._basicConfig(logging.INFO,
                          '%(asctime)s %(levelname)s %(name)s: %(message)s',
                          '%H:%M:%S')

    def _basicConfig(self, level, fmt, datefmt=None):
        """Configure logging."""
        stream = TextCtrlStream(self._log_ctrl)
        root = logging.RootLogger(level)
        manager = logging.Manager(root)
        formatter = logging.Formatter(fmt, datefmt)
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        root.addHandler(handler)
        # store member variables:
        self._log_stream = stream
        self._log_manager = manager

    def getLogger(self, name='root'):
        return self._log_manager.getLogger(name)

    def _read_stream(self, stream):
        # The file iterator seems to be buffered:
        for line in iter(stream.readline, b''):
            try:
                self._log_stream.write(line)
            except:
                break


class TextCtrlStream(object):

    """
    Write to a text control.
    """

    def __init__(self, ctrl):
        """Set text control."""
        self._ctrl = ctrl

    def write(self, text):
        """Append text."""
        wx.CallAfter(self._ctrl.WriteText, text)
