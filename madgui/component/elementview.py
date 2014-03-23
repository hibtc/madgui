# encoding: utf-8
"""
Contains a control class for the element detail view popup.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core import wx

# exported symbols
__all__ = ['ElementView']


class ElementView(object):

    """
    Control class for filling a TableDialog with beam line element details.
    """

    def __init__(self, popup, model, element_name):
        """Start to manage the popup window."""
        self.model = model
        self.element_name = element_name
        self.popup = popup
        self.update()
        model.hook.update.connect(self.update)
        self.popup.Bind(wx.EVT_CLOSE, self.OnClose)

    def OnClose(self, event):
        """Disconnect the manager, after the popup window was closed."""
        self.model.hook.update.disconnect(self.update)
        event.Skip()

    def update(self):

        """
        Update the contents of the managed popup window.
        """

        el = self.model.element_by_name(self.element_name)
        rows = el.items()

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
        order = ['Type',
                 'Name',
                 'Position',
                 'Length']
        order = dict(zip(order, range(-len(order), 0)))
        rows = sorted(rows, key=lambda row: order.get(row[0], len(order)))
        rows = filter(lambda row: row[0] not in ('Vary','Ksl','Knl'), rows)

        # add colon
        rows = [(k+':',v) for (k,v) in rows]

        # update view:
        self.popup.rows = rows
