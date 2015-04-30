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

# 3rd-party
from cpymad.model import Model

# internal
from madgui.core.plugin import HookCollection
from madgui.component.about import show_about_dialog
from madgui.component.beamdialog import BeamWidget
from madgui.component.lineview import TwissView, DrawLineElements
from madgui.component.modeldetail import ModelDetailWidget
from madgui.component.openmodel import OpenModelWidget
from madgui.component.session import Session, SegmentedRange
from madgui.component.twissdialog import ManageTwissWidget
from madgui.util import unit
from madgui.widget.figure import FigurePanel
from madgui.widget import menu
from madgui.widget.input import ShowModal

# exported symbols
__all__ = [
    'NotebookFrame',
    'set_frame_title',
]


def monospace(pt_size):
    """Return a monospace font."""
    return wx.Font(pt_size,
                   wx.FONTFAMILY_MODERN,
                   wx.FONTSTYLE_NORMAL,
                   wx.FONTWEIGHT_NORMAL)


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
        session = Session(self.madx_units)
        self._session = session
        threading.Thread(target=self._read_stream,
                         args=(session.remote_process.stdout,)).start()
        self.env.update({
            'session': session,
            'madx': session.madx,
            'libmadx': session.libmadx
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

    def _LoadModel(self, event=None):
        if OpenModelWidget.create(self):
            self._EditModelDetail()

    def _GenerateModel(self):
        session = self.env['session']
        madx = session.madx
        libmadx = session.libmadx

        optics = {'default': {'init-files': []}}
        sequences = {}
        beams = {}
        for seq in madx.sequences:
            ranges = {}
            ranges['ALL'] = {
                'madx-range': {'first': '#s', 'last': '#e'},
                'default-twiss': 'default',
                'twiss-initial-conditions': {
                    'default': {}
                }
            }
            # TODO: automatically read other used initial conditions from
            # MAD-X memory (if any TWISS table is present).
            seq_data = {
                'ranges': ranges,
                'default-range': 'ALL',
            }
            sequences[seq] = seq_data
            beam_name = 'beam{}'.format(len(beams))
            seq_data['beam'] = beam_name
            try:
                beam = libmadx.get_sequence_beam(seq)
            except RuntimeError:
                beam = {}
            beams[beam_name] = beam
            # TODO: automatically insert other beams from MAD-X memory

        data = {
            'api_version': 0,
            'path_offset': '',
            'init-files': '',
            'name': '(auto-generated)',
            'optics': optics,
            'sequences': sequences,
            'beams': beams,
            'default-sequence': sorted(sequences)[0],
            'default-optic': sorted(optics)[0],
        }
        return Model(data, repo=None, madx=madx)

    def _EditModelDetail(self, event=None):
        session = self.env['session']

        if session.model:
            cpymad_model = session.model
        else:
            cpymad_model = self._GenerateModel()

        utool = session.utool

        detail = {}
        retcode = ModelDetailWidget.ShowModal(self, model=cpymad_model,
                                              data=detail, utool=utool)
        if retcode != wx.ID_OK:
            return

        sequence = detail['sequence']
        beam = detail['beam']
        range_bounds = detail['range']
        twiss_args = detail['twiss']

        beam = dict(beam, sequence=sequence)
        twiss_args_no_unit = {k: utool.dict_strip_unit(v)
                              for k, v in twiss_args.items()}

        cpymad_model.sequences[sequence].init()
        session.madx.command.beam(**utool.dict_strip_unit(beam))

        segman = SegmentedRange(
            session=session,
            sequence=sequence,
            range=range_bounds,
        )
        segman.model = cpymad_model
        segman.indicators = detail['indicators']

        session.segman = segman
        segman.set_all(twiss_args)

        TwissView.create(session, self, basename='env')

    def _LoadMadxFile(self, event=None):
        """
        Dialog component to find/open a .madx file.
        """
        dlg = wx.FileDialog(
            self,
            style=wx.FD_OPEN,
            wildcard="MADX files (*.madx;*.str)|*.madx;*.str|All files (*.*)|*")
        if ShowModal(dlg) != wx.ID_OK:
            return
        path = dlg.Path

        madx = self.env['madx']
        num_seq = len(madx.sequences)
        madx.call(path, True)
        # if there are any new sequences, give the user a chance to view them
        # automatically:
        if len(madx.sequences) > num_seq:
            self._EditModelDetail()

    def _EditTwiss(self, event=None):
        segman = self.GetActiveFigurePanel().view.segman
        utool = self.madx_units
        elements = segman.elements
        twiss_initial = segman.twiss_initial.copy()
        retcode = ManageTwissWidget.ShowModal(self, utool=utool,
                                              elements=elements,
                                              data=twiss_initial,
                                              inactive={})
        if retcode == wx.ID_OK:
            segman.set_all(twiss_initial)

    def _SetBeam(self, event=None):
        segman = self.GetActiveFigurePanel().view.segman
        beam = segman.beam.copy()
        retcode = BeamWidget.ShowModal(self, utool=self.madx_units,
                                       data=segman.beam)
        if retcode == wx.ID_OK:
            segman.beam = beam


    def _ShowIndicators(self, event=None):
        panel = self.GetActiveFigurePanel()
        segman = panel.view.segman
        if segman.indicators:
            segman.indicators.destroy()
        else:
            segman.indicators = True
            DrawLineElements.create(panel).plot()
            panel.view.figure.draw()

    def _UpdateShowIndicators(self, event):
        segman = self.GetActiveFigurePanel().view.segman
        event.Check(bool(segman.indicators))

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
                Separator,
                MenuItem('&Open MAD-X file\tCtrl+O',
                         'Open a .madx file in this MAD-X session.',
                         self._LoadMadxFile),
                MenuItem('Load &model\tCtrl+M',
                         'Open a model in this MAD-X session.',
                         self._LoadModel),
                # TODO: save session/model
                Separator,
                MenuItem('&Close',
                         'Close window',
                         self.OnQuit,
                         id=wx.ID_CLOSE),
            ]),
            Menu('&View', [
                MenuItem('&Envelope',
                         'Open new tab with beam envelopes.',
                         lambda _: TwissView.create(self.env['session'],
                                                    self, basename='env')),
                MenuItem('&Position',
                         'Open new tab with beam position.',
                         lambda _: TwissView.create(self.env['session'],
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
            self._session.rpc_client.close()
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
        if not self.env['madx']:
            return
        enable_view = bool(self.env['madx'].sequences
                           or self.env['session'].model)
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
