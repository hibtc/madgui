# encoding: utf-8
"""
Notebook window component for MadGUI (main window).
"""

# force new style imports
from __future__ import absolute_import

# standard library
import sys
import logging
import threading

# GUI components
from madgui.core import wx
import wx.aui
from wx.py.shell import Shell

# internal
from madgui.core.plugin import HookCollection
from madgui.component.about import show_about_dialog
from madgui.component.beamdialog import BeamWidget
from madgui.component.lineview import TwissView, DrawLineElements
from madgui.component.model import Model
from madgui.component.session import Session, Segment
from madgui.component.twissdialog import TwissWidget
from madgui.resource.file import FileResource
from madgui.util import unit
from madgui.widget.figure import FigurePanel
from madgui.widget import menu
from madgui.widget.input import ShowModal, Cancellable, Dialog, CancelAction
from madgui.widget.filedialog import OpenDialog

# exported symbols
__all__ = [
    'NotebookFrame',
]


if sys.platform == 'win32':
    MDIParentFrame = wx.MDIParentFrame
    MDIChildFrame = wx.MDIChildFrame

    def ShowMDIChildFrame(frame):
        frame.Show()

    def GetMDIChildFrames(parent):
        return [window for window in parent.GetChildren()
                if isinstance(window, MDIChildFrame)]

else:
    MDIParentFrame = wx.aui.AuiMDIParentFrame
    MDIChildFrame = wx.aui.AuiMDIChildFrame

    def ShowMDIChildFrame(frame):
        frame.Layout()
        frame.Fit()
        frame.Activate()

    def GetMDIChildFrames(parent):
        return [window for window in parent.GetClientWindow().GetChildren()
                if isinstance(window, MDIChildFrame)]


def CloseMDIChildren(parent):
    """Close all child frames to prevent a core dump on wxGTK."""
    for window in GetMDIChildFrames(parent):
        window.Destroy()


def monospace(pt_size):
    """Return a monospace font."""
    return wx.Font(pt_size,
                   wx.FONTFAMILY_MODERN,
                   wx.FONTSTYLE_NORMAL,
                   wx.FONTWEIGHT_NORMAL)


class NotebookFrame(MDIParentFrame):

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
            menu='madgui.widget.notebook.menu',
            reset=None,
        )

        super(NotebookFrame, self).__init__(
            None, -1,
            title='MadGUI',
            size=wx.Size(800, 600))

        self.views = []
        self.app = app
        self.env = {
            'frame': self,
            'views': self.views,
            'session': None,
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
        self.session = Session(self.madx_units)
        self.session.start()
        threading.Thread(target=self._read_stream,
                         args=(self.session.remote_process.stdout,)).start()

    def CreateControls(self):
        # create notebook
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        statusbar = self.CreateStatusBar()
        statusbar.SetFont(monospace(10))

        # create menubar and listen to events:
        self.SetMenuBar(self._CreateMenu())
        # Create a command tab
        self._NewLogTab()

    @Cancellable
    def _LoadModel(self, event=None):
        reset = self._ConfirmResetSession()
        wildcards = [("cpymad model files", "*.cpymad.yml"),
                     ("All files", "*")]
        dlg = OpenDialog(self, "Open model", wildcards)
        dlg.Directory = self.app.conf.get('model_path', '.')
        with dlg:
            ShowModal(dlg)
            filename = dlg.Filename
            directory = dlg.Directory

        repo = FileResource(directory)
        mdata = repo.yaml(filename, encoding='utf-8')

        if not mdata:
            return
        if reset:
            self._ResetSession()
        Model.init(data=mdata, repo=repo, madx=self.session.madx)
        self.session.model = mdata
        self.session.repo = repo
        self._EditModelDetail()

    def _UpdateModel(self, known_sequences):
        session = self.session
        madx = session.madx

        # Don't do anything if a sequence is already shown (but update?!)
        if session.model is not None:
            return

        # TODO: diff on configurations rather than sequences
        if set(madx.sequences) <= set(known_sequences):
            # TODO: INFO("No new sequences/configurations.")
            pass

        models = Model.detect(madx)
        if not models:
            # TODO: INFO("No configuration can be detected.")
            return

        self._EditModelDetail()

    @Cancellable
    def _EditModelDetail(self, models=None):
        # TODO: dialog to choose among models + summary + edit subpages
        session = self.session
        model = session.model
        utool = session.utool

        segment = Segment(
            session=session,
            sequence=model['sequence'],
            range=model['range'],
            twiss_args=utool.dict_add_unit(model['twiss']),
        )
        segment.model = model
        segment.show_element_indicators = model.get('indicators', True)
        TwissView.create(session, self, basename='env')

    @Cancellable
    def _LoadMadxFile(self, event=None):
        """
        Dialog component to find/open a .madx file.
        """
        reset = self._ConfirmResetSession()
        wildcards = [("MAD-X files", "*.madx", "*.str"),
                     ("All files", "*")]
        dlg = OpenDialog(self, 'Load MAD-X file', wildcards)
        with dlg:
            ShowModal(dlg)
            path = dlg.Path
            directory = dlg.Directory

        if reset:
            self._ResetSession()

        madx = self.session.madx
        old_sequences = list(madx.sequences)
        madx.call(path, True)

        # if there are any new sequences, give the user a chance to view them
        # automatically:
        self._UpdateModel(old_sequences)


    @Cancellable
    def _EditTwiss(self, event=None):
        segment = self.GetActiveFigurePanel().view.segment
        utool = self.madx_units
        with Dialog(self) as dialog:
            widget = TwissWidget(dialog, utool=utool)
            segment.twiss_args = widget.Query(segment.twiss_args)

    @Cancellable
    def _SetBeam(self, event=None):
        segment = self.GetActiveFigurePanel().view.segment
        with Dialog(self) as dialog:
            widget = BeamWidget(dialog, utool=self.madx_units)
            segment.beam = widget.Query(segment.beam)

    def _ShowIndicators(self, event):
        panel = self.GetActiveFigurePanel()
        segment = panel.view.segment
        segment.show_element_indicators = event.Checked()

    def _UpdateShowIndicators(self, event):
        segment = self.GetActiveFigurePanel().view.segment
        event.Check(bool(segment.show_element_indicators))

    def _ConfirmResetSession(self):
        """Prompt the user to confirm resetting the current session."""
        if not self.session.model:
            return False
        question = (
            'Reset MAD-X session? Unsaved changes will be lost.\n\n'
            'Note: it is recommended to reset MAD-X before loading a new '
            'model or sequence into memory, since MAD-X might crash on a '
            'naming conflict.\n\n'
            'Press Cancel to abort action.'
        )
        answer = wx.MessageBox(
            question, 'Reset session',
            wx.YES_NO | wx.CANCEL | wx.YES_DEFAULT | wx.ICON_QUESTION,
            parent=self)
        if answer == wx.YES:
            return True
        if answer == wx.NO:
            return False
        raise CancelAction

    def _ResetSession(self, event=None):
        CloseMDIChildren(self)
        self.session.stop()
        self._NewLogTab()
        self.InitMadx()
        self.hook.reset()

    def _CreateMenu(self):
        """Create a menubar."""
        # TODO: this needs to be done more dynamically. E.g. use resource
        # files and/or a plugin system to add/enable/disable menu elements.
        MenuItem = menu.Item
        Menu = menu.Menu
        Separator = menu.Separator

        menubar = self.menubar = wx.MenuBar()
        menu.extend(self, menubar, [
            Menu('&Session', [
                MenuItem('&New session window\tCtrl+N',
                         'Open a new session window',
                         self.OnNewWindow),
                MenuItem('&Python shell\tCtrl+P',
                         'Open a tab with a python shell',
                         self._NewCommandTab),
                Separator,
                MenuItem('&Open MAD-X file\tCtrl+O',
                         'Open a .madx file in this MAD-X session.',
                         self._LoadMadxFile),
                MenuItem('Load &model\tCtrl+M',
                         'Open a model in this MAD-X session.',
                         self._LoadModel),
                # TODO: save session/model
                Separator,
                MenuItem('&Reset session',
                         'Clear the MAD-X session state.',
                         self._ResetSession),
                Separator,
                MenuItem('&Close',
                         'Close window',
                         self.OnQuit,
                         id=wx.ID_CLOSE),
            ]),
            Menu('&View', [
                MenuItem('&Envelope',
                         'Open new tab with beam envelopes.',
                         lambda _: TwissView.create(self.session,
                                                    self, basename='env')),
                MenuItem('&Position',
                         'Open new tab with beam position.',
                         lambda _: TwissView.create(self.session,
                                                    self, basename='pos')),
            ]),
            Menu('&Manage', [
                MenuItem('&Initial conditions',
                         'Add/remove/edit TWISS initial conditions.',
                         self._EditTwiss),
                MenuItem('&Beam',
                         'Set beam.',
                         self._SetBeam),
                Separator,
                MenuItem('Show &element indicators',
                         'Show indicators for beam line elements.',
                         self._ShowIndicators,
                         self._UpdateShowIndicators,
                         wx.ITEM_CHECK),
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
        child = MDIChildFrame(self, -1, title)
        panel = FigurePanel(child, view)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(panel, 1, wx.EXPAND)
        child.SetSizer(sizer)
        def OnPageClose(event):
            self.views.remove(view)
            event.Skip()
        child.Bind(wx.EVT_CLOSE, OnPageClose)
        ShowMDIChildFrame(child)

        view.plot()
        self.views.append(view)
        return panel

    def GetActivePanel(self):
        """Return the Panel which is currently active."""
        if self.GetActiveChild():
            return self.GetActiveChild().GetChildren()[0]

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
            self.session.stop()
        except IOError:
            # The connection may already be terminated in case MAD-X crashed.
            pass
        CloseMDIChildren(self)
        event.Skip()

    def OnLogTabClose(self, event):
        """Prevent the command tab from closing, if other tabs are open."""
        if self.views:
            event.Veto()
        else:
            self.Close()

    def OnQuit(self, event):
        """Close the window."""
        self.Close()

    def OnUpdateMenu(self, event):
        if not self.session.madx:
            return
        enable_view = bool(self.session.madx.sequences or self.session.model)
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

    def _NewCommandTab(self, event=None):
        """Open a new command tab."""
        child = MDIChildFrame(self, -1, "Command")
        crust = Shell(child, locals=self.env)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(crust, 1, wx.EXPAND)
        child.SetSizer(sizer)
        ShowMDIChildFrame(child)

    def _NewLogTab(self):
        child = MDIChildFrame(self, -1, "Log")
        # Create a tab for logging
        textctrl = wx.TextCtrl(child, wx.ID_ANY,
                               style=wx.TE_MULTILINE|wx.TE_READONLY)
        textctrl.SetFont(monospace(10))
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(textctrl, 1, wx.EXPAND)
        child.SetSizer(sizer)
        child.Bind(wx.EVT_CLOSE, self.OnLogTabClose)
        ShowMDIChildFrame(child)
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
