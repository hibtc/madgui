"""
Info boxes to display element detail.
"""

from madqt.widget.params import TabParamTables

# TODO: updating an element calls into ds.get() 3 times!

__all__ = [
    'ElementInfoBox',
]


class ElementInfoBox(TabParamTables):

    def __init__(self, segment, el_id, **kwargs):
        datastore = segment.get_elem_ds(el_id)
        super(ElementInfoBox, self).__init__(datastore, **kwargs)

        self.segment = segment
        self.el_id = el_id
        self.segment.updated.connect(self.update)

    def closeEvent(self, event):
        self.segment.updated.disconnect(self.update)
        event.accept()

    @property
    def el_id(self):
        return self._el_id

    @el_id.setter
    def el_id(self, name):
        self._el_id = name
        self.update()

    @property
    def element(self):
        return self.segment.elements[self.el_id]

    def update(self):
        """
        Update the contents of the managed popup window.
        """
        # FIXME: this does not update substores/tabs
        if hasattr(self, 'segment'):
            self.datastore = self.segment.get_elem_ds(self.el_id)
        super(ElementInfoBox, self).update()
