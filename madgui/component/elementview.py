# encoding: utf-8
"""
Contains a control class for the element detail view popup.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core import wx
from madgui.core.plugin import HookCollection
from madgui.util.unit import strip_unit

# exported symbols
__all__ = ['ElementView']


# TODO: change style for active/inactive element markers


class ElementMarker(object):

    def __init__(self, line_view, elem_view):
        self._line_view = line_view
        self._elem_view = elem_view
        self._model = line_view.segman
        self._lines = []
        self._elem_view.hook.set_element.connect(self.update)
        self._elem_view.hook.close.connect(self.remove)
        self.update()
        line_view.hook.plot_ax.connect(self.plot_ax)

    def update(self):
        self._clear()
        line_view = self._line_view
        self.plot_ax(line_view.axes[line_view.xname], line_view.xname)
        self.plot_ax(line_view.axes[line_view.yname], line_view.yname)
        line_view.figure.draw()

    def _clear(self):
        for line in self._lines:
            line.remove()
        self._lines = []

    def remove(self):
        self._clear()
        self._line_view.hook.plot_ax.disconnect(self.plot_ax)
        self._line_view.figure.draw()
        self._elem_view.hook.set_element.disconnect(self.update)
        self._elem_view.hook.close.disconnect(self.remove)

    @property
    def element(self):
        return self._elem_view.element

    def plot_ax(self, axes, name):
        """Draw the elements into the canvas."""
        line_view = self._line_view
        unit_s = line_view.unit[line_view.sname]
        line_style = line_view.config['select_style']
        patch_x = strip_unit(self.element['at'], unit_s)
        self._lines.append(axes.axvline(patch_x, **line_style))


class ElementView(object):

    """
    Control class for filling a TableDialog with beam line element details.
    """

    def __init__(self, popup, model, element_name):
        """Start to manage the popup window."""
        self.hook = HookCollection(
            set_element=None,
            close=None)

        self.model = model
        self.popup = popup
        self._closed = False
        model.hook.update.connect(self.update)
        self.popup.Bind(wx.EVT_CLOSE, self.OnClose)
        # this comes last, as it implies an update
        self.element_name = element_name

    def OnClose(self, event):
        """Disconnect the manager, after the popup window was closed."""
        self.model.hook.update.disconnect(self.update)
        self._closed = True
        self.hook.close()
        event.Skip()

    def __nonzero__(self):
        return not self._closed
    __bool__ = __nonzero__

    @property
    def element_name(self):
        return self._element_name

    @element_name.setter
    def element_name(self, name):
        self._element_name = name
        self.hook.set_element()
        self.update()

    @property
    def element(self):
        elements = self.model.simulator.madx.active_sequence.elements
        raw_element = elements[self.element_name]
        return self.model.simulator.utool.dict_add_unit(raw_element)

    def update(self):

        """
        Update the contents of the managed popup window.
        """

        el = self.element
        rows = list(el.items())

        # convert to title case:
        rows = [(k.title(),v) for (k,v) in rows]

        # substitute nicer names:
        substitute = {'L': 'Length',
                      'At': 'Position'}
        rows = [(substitute.get(k,k),v) for (k,v) in rows]

        # presort alphanumerically:
        # (with some luck the order on the elements with equal key in the
        # subsequent sort will be left invariant)
        rows = sorted(rows)

        # sort preferred elements to top:
        order = ['Name',
                 'Type',
                 'Position',
                 'Length']
        order = dict(zip(order, range(-len(order), 0)))
        rows = sorted(rows, key=lambda row: order.get(row[0], len(order)))
        rows = filter(lambda row: row[0] not in ('Vary','Ksl','Knl'), rows)

        # update view:
        self.popup.rows = rows
