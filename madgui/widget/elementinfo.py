"""
Info boxes to display element detail.
"""

from collections import OrderedDict

from madgui.qt import QtGui
from madgui.core.base import Signal
from madgui.util.qt import fit_button
from madgui.util.layout import VBoxLayout, HBoxLayout
from madgui.core.model import ElementDataStore
from madgui.widget.params import TabParamTables, ParamTable

# TODO: updating an element calls into ds.get() 3 times!

__all__ = [
    'ElementInfoBox',
]


class ElementInfoBox(QtGui.QWidget):

    changed_element = Signal()
    _el_id = None

    def __init__(self, model, el_id, **kwargs):
        super().__init__()

        self.notebook = TabParamTables([
            ('Basic', ParamTable(BasicDataStore(model, 'element'))),
            ('Full', ParamTable(ElementDataStore(model, 'element'))),
            ('Twiss', ParamTable(TwissDataStore(model, 'twiss'))),
            ('Sigma', ParamTable(SigmaDataStore(model, 'sigma'))),
        ])

        # navigation
        self.select = QtGui.QComboBox()
        self.select.addItems([elem.Name for elem in model.elements])
        self.select.currentIndexChanged.connect(self.set_element)

        self.model = model
        self.el_id = el_id
        self.model.twiss.updated.connect(self.notebook.update)

        button_left = QtGui.QPushButton("<")
        button_right = QtGui.QPushButton(">")
        button_left.clicked.connect(lambda: self.advance(-1))
        button_right.clicked.connect(lambda: self.advance(+1))

        fit_button(button_left)
        fit_button(button_right)

        self.setLayout(VBoxLayout([
            HBoxLayout([button_left, self.select, button_right]),
            self.notebook,
        ], tight=True))


    def closeEvent(self, event):
        self.model.twiss.updated.disconnect(self.notebook.update)
        event.accept()

    def advance(self, step):
        elements  = self.model.elements
        old_index = self.model.get_element_index(self.el_id)
        new_index = old_index + step
        new_el_id = elements[new_index % len(elements)].El_id
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
            self.select.setCurrentIndex(self.model.get_element_index(self.el_id))
            self.notebook.kw['elem_index'] = self.el_id
            self.notebook.update()
            self.changed_element.emit()

    @property
    def element(self):
        return self.model.elements[self.el_id]

    # for dialog.save/load:
    @property
    def datastore(self):
        return self.notebook.currentWidget().datastore


class BasicDataStore(ElementDataStore):

    def _get(self):
        data = self.model.elements[self.kw['elem_index']]
        show = self.conf['show']
        return OrderedDict([
            (k, data[k])
            for k in show['common'] + show.get(data['type'], [])
        ])


class TwissDataStore(ElementDataStore):

    def _get(self):
        return self.model.get_elem_twiss(self.kw['elem_index'])

    def mutable(self, key):
        return False


class SigmaDataStore(TwissDataStore):

    def _get(self):
        return self.model.get_elem_sigma(self.kw['elem_index'])
