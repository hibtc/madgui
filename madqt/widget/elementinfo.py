"""
Info boxes to display element detail.
"""

from madqt.qt import QtGui
from madqt.core.base import Signal
from madqt.util.layout import VBoxLayout, HBoxLayout
from madqt.widget.params import TabParamTables

# TODO: updating an element calls into ds.get() 3 times!

__all__ = [
    'ElementInfoBox',
]


class ElementInfoBox(QtGui.QWidget):

    changed_element = Signal()
    _el_id = None

    def __init__(self, segment, el_id, **kwargs):
        super().__init__()

        datastore = segment.get_elem_ds(el_id)
        self.tab = TabParamTables(datastore, **kwargs)

        # navigation
        self.select = QtGui.QComboBox()
        self.select.addItems([elem['name'] for elem in segment.elements])
        self.select.currentIndexChanged.connect(self.set_element)

        button_left = QtGui.QPushButton("<")
        button_right = QtGui.QPushButton(">")
        button_left.clicked.connect(lambda: self.advance(-1))
        button_right.clicked.connect(lambda: self.advance(+1))

        self.setLayout(VBoxLayout([
            HBoxLayout([button_left, self.select, button_right]),
            self.tab,
        ], tight=True))

        self.segment = segment
        self.el_id = el_id
        self.segment.twiss.updated.connect(self.update)

    def closeEvent(self, event):
        self.segment.twiss.updated.disconnect(self.update)
        event.accept()

    def advance(self, step):
        elements  = self.segment.elements
        old_index = self.segment.get_element_index(self.el_id)
        new_index = old_index + step
        new_el_id = elements[new_index % len(elements)]['el_id']
        self.el_id = new_el_id

    @property
    def el_id(self):
        return self._el_id

    @el_id.setter
    def el_id(self, name):
        self.set_element(name)

    def set_element(self, name):
        if name != self._el_id:
            self._el_id = name
            self.update()
            self.changed_element.emit()

    @property
    def element(self):
        return self.segment.elements[self.el_id]

    def update(self):
        """
        Update the contents of the managed popup window.
        """
        # FIXME: this does not update substores/tabs
        if hasattr(self, 'segment'):
            self.tab.datastore = self.segment.get_elem_ds(self.el_id)
            self.select.setCurrentIndex(self.segment.get_element_index(self.el_id))
        super().update()
