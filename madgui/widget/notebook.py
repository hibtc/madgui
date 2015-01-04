# encoding: utf-8
"""
Notebook window component for MadGUI (main window).
"""

# force new style imports
from __future__ import absolute_import

# standard library
import logging
import threading

# GUI components
from madgui.core import wx
import wx.aui
from wx.py.crust import Crust

# internal
from madgui.widget.figure import FigurePanel
from madgui.core.plugin import HookCollection
from madgui.component.model import Simulator, Segment
from madgui.util import unit

# exported symbols
__all__ = ['NotebookFrame']


def monospace(pt_size):
    """Return a monospace font."""
    return wx.Font(pt_size,
                   wx.FONTFAMILY_MODERN,
                   wx.FONTSTYLE_NORMAL,
                   wx.FONTWEIGHT_NORMAL)


class MenuItem(object):

    def __init__(self, title, description, action, id=wx.ID_ANY):
        self.title = title
        self.action = action
        self.description = description
        self.id = id

    def append_to(self, menu, evt_handler):
        item = menu.Append(self.id, self.title, self.description)
        evt_handler.Bind(wx.EVT_MENU, self.action, item)


class Menu(object):

    def __init__(self, title, items):
        self.title = title
        self.items = items

    def append_to(self, menu, evt_handler):
        submenu = wx.Menu()
        menu.Append(submenu, self.title)
        extend_menu(evt_handler, submenu, self.items)


class Separator(object):

    @classmethod
    def append_to(cls, menu, evt_handler):
        menu.AppendSeparator()


def extend_menu(evt_handler, menu, items):
    """
    Append menu items to menu.
    """
    for item in items:
        item.append_to(menu, evt_handler)


class NotebookFrame(wx.Frame):

    """
    Notebook window class for MadGUI (main window).
    """

    def __init__(self, app, show=True):

        """
        Create notebook frame.

        Extends wx.Frame.__init__.
        """

        self.hook = HookCollection(
            init='madgui.widget.notebook.init',
            menu='madgui.widget.notebook.menu')

        super(NotebookFrame, self).__init__(
            parent=None,
            title='MadGUI',
            size=wx.Size(800, 600))

        self.app = app
        self.env = {
            'frame': self,
            'views': [],
            'madx': None,
            'libmadx': None,
        }

        self.CreateControls()
        self.InitMadx()
        self.Show(show)

    def InitMadx(self):
        """
        Start a MAD-X interpreter and associate with this frame.
        """
        # TODO: close old client + shutdown _read_stream thread.
        self.madx_units = unit.UnitConverter(
            unit.from_config_dict(self.app.conf['madx_units']))
        simulator = Simulator(self.madx_units)
        self._simulator = simulator
        threading.Thread(target=self._read_stream,
                         args=(simulator.remote_process.stdout,)).start()
        self.env.update({
            'simulator': simulator,
            'madx': simulator.madx,
            'libmadx': simulator.libmadx
        })


    def CreateControls(self):
        # create notebook
        self.Bind(wx.EVT_CLOSE, self.OnClose)
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
        statusbar = self.CreateStatusBar()
        statusbar.SetFont(monospace(10))

        # create menubar and listen to events:
        self.SetMenuBar(self._CreateMenu())
        # Create a command tab
        self._NewCommandTab()

    def _LoadMadxFile(self):
        """
        Dialog component to find/open a .madx file.
        """
        dlg = wx.FileDialog(
            self,
            style=wx.FD_OPEN,
            wildcard="MADX files (*.madx;*.str)|*.madx;*.str|All files (*.*)|*")
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.Path
        finally:
            dlg.Destroy()

        madx = frame.env['madx']
        madx.call(path, True)

    def _CreateMenu(self):
        """Create a menubar."""
        # TODO: this needs to be done more dynamically. E.g. use resource
        # files and/or a plugin system to add/enable/disable menu elements.
        from madgui.component.about import show_about_dialog
        from madgui.component.beamdialog import BeamDialog
        from madgui.component.twissdialog import TwissDialog
        from madgui.component.lineview import TwissView
        from madgui.component.openmodel import OpenModelDlg

        def set_twiss(event):
            # TODO: get initial segment for current TAB
            segment = None
            twiss_args = TwissDialog.show_modal(self, self.madx_units,
                                                segment.twiss_args)
            if twiss_args is not None:
                segment.twiss_args = twiss_args
                segment.twiss()

        def set_beam(event):
            # TODO: get initial segment for current TAB
            segment = None
            beam = BeamDialog.show_modal(self, self.madx_units, segment.beam)
            if beam_args is not None:
                segment.beam = beam
                segment.twiss()

        menubar = self.menubar = wx.MenuBar()
        extend_menu(self, menubar, [
            Menu('&Window', [
                MenuItem('&New\tCtrl+N',
                         'Open a new window',
                         self.OnNewWindow),
                Separator,
                MenuItem('Load &MAD-X file\tCtrl+O',
                         'Open a .madx file in this frame.',
                         lambda _: self._LoadMadxFile()),
                MenuItem('&Open model\tCtrl+M',
                         'Open a model in this frame.',
                         lambda _: OpenModelDlg.create(self)),
                Separator,
                MenuItem('&Close',
                         'Close window',
                         self.OnQuit,
                         wx.ID_CLOSE),
            ]),
            Menu('&View', [
                MenuItem('Beam &envelope',
                         'Open new tab with beam envelopes.',
                         lambda _: TwissView.create(self.env['simulator'],
                                                    self, basename='env')),
                MenuItem('Beam &position',
                         'Open new tab with beam position.',
                         lambda _: TwissView.create(self.env['simulator'],
                                                    self, basename='pos')),
            ]),
            Menu('&Tab', [
                MenuItem('&TWISS',
                         'Set TWISS initial conditions.',
                         set_twiss),
                MenuItem('&Beam',
                         'Set beam.',
                         set_beam),
            ]),
            Menu('&Help', [
                MenuItem('&About',
                         'Show about dialog.',
                         lambda _: show_about_dialog(self)),
            ]),
        ])

        # Create menu items
        self.hook.menu(self, menubar)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateMenu, menubar)
        self._IsEnabledTop = {self.ViewMenuIndex: True,
                              self.TabMenuIndex: True}
        return menubar

    @property
    def ViewMenuIndex(self):
        return 1

    @property
    def TabMenuIndex(self):
        return 2

    def OnNewWindow(self, event):
        """Open a new frame."""
        self.__class__(self.app)

    def AddView(self, view, title):
        """Add new notebook tab for the view."""
        # TODO: remove this method in favor of a event based approach?
        panel = FigurePanel(self.notebook, view)
        self.notebook.AddPage(panel, title, select=True)
        view.plot()
        self.env['views'].append(view)
        return panel

    def GetActivePanel(self):
        """Return the Panel which is currently active."""
        return self.notebook.GetPage(self.notebook.GetSelection())

    def GetActiveFigurePanel(self):
        """Return the FigurePanel which is currently active or None."""
        panel = self.GetActivePanel()
        if isinstance(panel, FigurePanel):
            return panel
        return None

    def OnClose(self, event):
        # We want to terminate the remote session, otherwise _read_stream
        # may hang:
        try:
            self._simulator.rpc_client.close()
        except IOError:
            # The connection may already be terminated in case MAD-X crashed.
            pass
        event.Skip()

    def OnPageClose(self, event):
        """Prevent the command tab from closing, if other tabs are open."""
        page = self.notebook.GetPage(event.Selection)
        if page is self._command_tab and self.notebook.GetPageCount() > 1:
            event.Veto()

    def OnPageClosed(self, event):
        """A page has been closed. If it was the last, close the frame."""
        if self.notebook.GetPageCount() == 0:
            self.Close()
        else:
            del self.env['views'][event.Selection - 1]

    def OnQuit(self, event):
        """Close the window."""
        self.Close()

    def OnUpdateMenu(self, event):
        enable_view = bool(self.env['madx'].sequences
                           or self.env['simulator'].model)
        # we only want to call EnableTop() if the state is actually
        # different from before, since otherwise this will cause very
        # irritating flickering on windows. Because menubar.IsEnabledTop is
        # bugged on windows, we need to keep track ourself:
        # if enable != self.menubar.IsEnabledTop(idx):
        view_menu_index = self.ViewMenuIndex
        if enable_view != self._IsEnabledTop[view_menu_index]:
            self.menubar.EnableTop(view_menu_index, enable_view)
            self._IsEnabledTop[view_menu_index] = enable_view
        # Enable/Disable &Tab menu
        enable_tab = bool(self.GetActiveFigurePanel())
        tab_menu_index = self.TabMenuIndex
        if enable_tab != self._IsEnabledTop[tab_menu_index]:
            self.menubar.EnableTop(tab_menu_index, enable_tab)
            self._IsEnabledTop[tab_menu_index] = enable_tab
        event.Skip()

    def _NewCommandTab(self):
        """Open a new command tab."""
        crust = Crust(self.notebook, locals=self.env)
        self.notebook.AddPage(crust, "Command", select=True)
        self._command_tab = crust
        # Create a tab for logging
        nb = crust.notebook
        panel = wx.Panel(nb, wx.ID_ANY)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)
        textctrl = wx.TextCtrl(panel, wx.ID_ANY,
                               style=wx.TE_MULTILINE|wx.TE_READONLY)
        textctrl.SetFont(monospace(10))
        sizer.Add(textctrl, 1, wx.EXPAND)
        nb.AddPage(panel, "Log", select=True)
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


def set_frame_title(model, frame):
    """
    Set the frame title to the model name.

    This is invoked as a hook from ``model.hook.show(frame)``.
    """
    frame.SetTitle(model.name)


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
