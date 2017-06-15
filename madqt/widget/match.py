# encoding: utf-8
"""
UI for matching.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from pkg_resources import resource_filename

from madqt.qt import QtGui, uic
from madqt.widget.tableview import ColumnInfo
from madqt.correct.match import variable_from_knob, Constraint
from madqt.widget.quantity import DoubleValidator


class MatchWidget(QtGui.QWidget):

    ui_file = 'match.ui'

    constraints_columns = [
        ColumnInfo("Element", lambda c: c.elem['name'] if c.elem else "(global)"),
        ColumnInfo("Name", 'axis'),
        ColumnInfo("Target", 'value'),
    ]

    variables_columns = [
        ColumnInfo("Element", lambda v: v.elem['name'] if v.elem else ""),
        ColumnInfo("Expression", 'expr'),
        ColumnInfo("Design", 'design'),
        ColumnInfo("Target", lambda v: v.value),
    ]

    def __init__(self, matcher):
        super(MatchWidget, self).__init__()
        uic.loadUi(resource_filename(__name__, self.ui_file), self)
        self.matcher = matcher
        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    # The three steps of UI initialization

    def init_controls(self):
        self.ctab.horizontalHeader().setHighlightSections(False)
        self.vtab.horizontalHeader().setHighlightSections(False)
        self.ctab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.vtab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.ctab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.vtab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.ctab.set_columns(self.constraints_columns, self.matcher.constraints)
        self.vtab.set_columns(self.variables_columns, self.matcher.variables)

    def set_initial_values(self):
        pass

    def connect_signals(self):
        self.ctab.selectionChangedSignal.connect(self.selection_changed_constraints)
        self.vtab.selectionChangedSignal.connect(self.selection_changed_variables)
        self.button_remove_constraint.clicked.connect(self.ctab.removeSelectedRows)
        self.button_remove_variable.clicked.connect(self.vtab.removeSelectedRows)
        self.button_clear_constraint.clicked.connect(self.matcher.constraints.clear)
        self.button_clear_variable.clicked.connect(self.matcher.variables.clear)
        self.button_add_constraint.clicked.connect(self.add_constraint)
        self.button_add_variable.clicked.connect(self.add_variable)
        self.matcher.constraints.update_after.connect(self.on_update_constraints)
        self.matcher.variables.update_after.connect(self.on_update_variables)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.buttonBox.clicked.connect(self.clicked)
        self.button_match.clicked.connect(self.matcher.match)
        # TODO: connect self.matcher.finished?

    def selection_changed_constraints(self):
        self.button_remove_constraint.setEnabled(bool(self.ctab.selectedIndexes()))

    def selection_changed_variables(self):
        self.button_remove_variable.setEnabled(bool(self.vtab.selectedIndexes()))

    def on_update_constraints(self, *args):
        self.button_clear_constraint.setEnabled(bool(self.matcher.constraints))

    def on_update_variables(self, *args):
        self.button_clear_variable.setEnabled(bool(self.matcher.variables))

    def accept(self):
        self.matcher.accept()
        self.window().accept()

    def reject(self):
        self.matcher.reject()
        self.window().reject()

    def clicked(self, button):
        role = self.buttonBox.buttonRole(button)
        if role == QtGui.QDialogButtonBox.ApplyRole:
            self.matcher.apply()

    def add_constraint(self):
        dialog = ConstraintDialog(self.window(), self.matcher)
        status = dialog.exec_()
        if status == QtGui.QDialog.Accepted:
            elem = self.matcher.segment.get_element_by_name(
                dialog.combo_element.currentText())
            self.matcher.constraints.append(Constraint(
                elem, elem['at'] + elem['l'],
                dialog.combo_name.currentText(),
                float(dialog.edit_value.text()),
            ))

    def add_variable(self):
        text, ok = QtGui.QInputDialog.getText(
            self.window(), "Add new variable", "Knob:")
        if ok and text:
            self.matcher.variables.append(
                variable_from_knob(self.matcher, text))

class ConstraintDialog(QtGui.QDialog):

    def __init__(self, parent, matcher):
        super(ConstraintDialog, self).__init__(parent)
        uic.loadUi(resource_filename(__name__, 'addconstraint.ui'), self)
        self.setWindowTitle("New constraint")
        self.matcher = matcher
        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    def init_controls(self):
        self.combo_element.addItems([
            el['name'] for el in self.matcher.segment.elements
        ])
        self.combo_name.addItems(
            self.matcher.segment.workspace.config['matching']['element'])
        self.edit_value.setValidator(DoubleValidator())

    def set_initial_values(self):
        pass

    def connect_signals(self):
        pass
