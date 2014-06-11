# encoding: utf-8
"""
Matching tool for a :class:`LineView` instance.
"""

# force new style imports
from __future__ import absolute_import

# standard library
import re

# 3rd party
from cern.resource.package import PackageResource

# internal
from madgui.core import wx
from madgui.util.common import ivar
from madgui.util.plugin import HookCollection

# exported symbols
__all__ = ['MatchTool']


class MatchTool(object):

    """
    Controller that performs matching when clicking on an element.
    """

    hook = ivar(HookCollection,
                start='madgui.component.matching.start')


    def __init__(self, panel):
        """Add toolbar tool to panel and subscribe to capture events."""
        self.cid = None
        self.model = panel.view.model
        self.panel = panel
        self.view = panel.view
        self.matcher = None
        # toolbar tool
        res = PackageResource('madgui.resource')
        with res.open('cursor.xpm') as xpm:
            img = wx.ImageFromStream(xpm, wx.BITMAP_TYPE_XPM)
        bmp = wx.BitmapFromImage(img)
        self.toolbar = panel.toolbar
        self.tool = panel.toolbar.AddCheckTool(
                wx.ID_ANY,
                bitmap=bmp,
                shortHelp='Beam matching',
                longHelp='Match by specifying constraints for envelope x(s), y(s).')
        panel.Bind(wx.EVT_TOOL, self.OnMatchClick, self.tool)
        panel.Bind(wx.EVT_UPDATE_UI, self.UpdateTool, self.tool)
        # setup mouse capture
        panel.hook.capture_mouse.connect(self.stop_match)

    def UpdateTool(self, event):
        """Enable/disable toolbar tool."""
        self.tool.Enable(self.model.can_match)

    def OnMatchClick(self, event):
        """Invoked when user clicks Match-Button"""
        if event.IsChecked():
            self.start_match()
        else:
            self.stop_match()

    def start_match(self):
        """Start matching mode."""
        self.panel.hook.capture_mouse()
        self.cid = self.view.figure.canvas.mpl_connect(
                'button_press_event',
                self.on_match)
        self.matcher = Matching(self.model)
        self.hook.start(self.matcher, self.view)

    def stop_match(self):
        """Stop matching mode."""
        if self.cid is not None:
            self.view.figure.canvas.mpl_disconnect(self.cid)
            self.cid = None
            self.toolbar.ToggleTool(self.tool.Id, False)
            self.matcher.stop()

    def on_match(self, event):

        """
        Draw new constraint and perform matching.

        Invoked after the user clicks in matching mode.
        """

        axes = event.inaxes
        if axes is None:
            return
        name = self.view.get_axes_name(axes)
        conj = self.view.get_conjugate(name)

        elem = self.model.element_by_position(
            event.xdata * self.view.unit['s'])
        if elem is None or 'name' not in elem:
            return

        if event.button == 2:
            self.matcher.remove_constraint(elem)
            return
        elif event.button != 1:
            return

        orig_cursor = self.panel.GetCursor()
        wait_cursor = wx.StockCursor(wx.CURSOR_WAIT)
        self.panel.SetCursor(wait_cursor)

        # add the clicked constraint
        envelope = event.ydata * self.view.unit[name]
        self.matcher.add_constraint(name, elem, envelope)

        # add another constraint to hold the orthogonal axis constant
        orth_env = self.model.get_twiss_center(elem, conj)
        self.matcher.add_constraint(conj, elem, orth_env)

        self.matcher.match()
        self.panel.SetCursor(orig_cursor)


class MatchTransform(object):

    def __init__(self, model):
        self._ex = model.summary.ex
        self._ey = model.summary.ey

    def envx(self, val):
        return 'betx', val*val/self._ex

    def envy(self, val):
        return 'bety', val*val/self._ey

    def x(self, val):
        return 'x', val

    def y(self, val):
        return 'y', val


class Matching(object):

    hook = ivar(HookCollection,
                stop=None,
                add_constraint=None,
                remove_constraint=None,
                clear_constraints=None)

    def __init__(self, model):
        self.model = model
        self.constraints = []

    def stop(self):
        self.clear_constraints()
        self.hook.stop()

    def match(self):

        """Perform matching according to current constraints."""

        model = self.model

        # select variables: one for each constraint
        vary = []
        allvars = [elem for elem in model.elements
                   if elem.type.lower() == 'quadrupole']
        for axis,elem,envelope in self.constraints:
            at = elem.at
            allowed = [v for v in allvars if v.at < at]
            try:
                v = max(allowed, key=lambda v: v.at)
                try:
                    expr = v.k1._expression
                except AttributeError:
                    expr = v.name + +'->k1'
                vary.append(expr)
                allvars.remove(v)
            except ValueError:
                # No variable in range found! Ok.
                pass

        trans = MatchTransform(model)

        # select constraints
        constraints = []
        ex, ey = model.summary.ex, model.summary.ey
        for axis,elem,envelope in self.constraints:
            name, val = getattr(trans, axis)(envelope)
            el_name = re.sub(':\d+$', '', elem.name)
            constraints.append({
                'range': el_name,
                name: model.utool.value_to_madx(name, val)})

        twiss_args = model.utool.dict_to_madx(model.twiss_args)
        model.madx.match(sequence=model.name,
                         vary=vary,
                         constraints=constraints,
                         twiss_init=twiss_args)
        model.twiss()

    def find_constraint(self, elem, axis=None):
        """Find and return the constraint for the specified element."""
        matched = [c for c in self.constraints if c[1] == elem]
        if axis is not None:
            matched = [c for c in matched if c[0] == axis]
        return matched

    def add_constraint(self, axis, elem, envelope):
        """Add constraint and perform matching."""
        existing = self.find_constraint(elem, axis)
        if existing:
            self.remove_constraint(elem, axis)
        self.constraints.append( (axis, elem, envelope) )
        self.hook.add_constraint()

    def remove_constraint(self, elem, axis=None):
        """Remove the constraint for elem."""
        self.constraints = [
            c for c in self.constraints
            if c[1].name != elem.name or (axis is not None and c[0] != axis)]
        self.hook.remove_constraint()

    def clear_constraints(self):
        """Remove all constraints."""
        self.constraints = []
        self.hook.clear_constraints()
