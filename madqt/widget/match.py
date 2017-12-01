"""
UI for matching.
"""

from pkg_resources import resource_filename

from madqt.qt import QtGui, uic
from madqt.widget.tableview import ColumnInfo, ExtColumnInfo
from madqt.correct.match import variable_from_knob, Constraint



def get_constraint_elem(matcher, c, i):
    return matcher.elem_enum(c.elem['name'] if c.elem else "(global)")

def set_constraint_elem(matcher, c, i, name):
    if name is not None:
        el = matcher.segment.elements[str(name)]
        matcher.constraints[i] = Constraint(el, el['at']+el['l'], c.axis, c.value)

def get_constraint_axis(matcher, c, i):
    return matcher.lcon_enum(c.axis)

def set_constraint_axis(matcher, c, i, axis):
    if axis is not None:
        value = matcher.segment.get_twiss(c.elem['name'], str(axis), c.pos)
        matcher.constraints[i] = Constraint(c.elem, c.pos, str(axis), value)

def set_constraint_value(matcher, c, i, value):
    if value is not None:
        matcher.constraints[i] = Constraint(c.elem, c.pos, c.axis, value)


class MatchWidget(QtGui.QWidget):

    ui_file = 'match.ui'

    constraints_columns = [
        ExtColumnInfo("Element", get_constraint_elem, set_constraint_elem,
                      resize=QtGui.QHeaderView.Stretch),
        ExtColumnInfo("Name", get_constraint_axis, set_constraint_axis),
        ExtColumnInfo("Target", 'value', set_constraint_value),
    ]

    variables_columns = [
        ColumnInfo("Element", lambda v: v.elem['name'] if v.elem else "",
                   resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("Expression", 'expr'),
        ColumnInfo("Design", 'design'),
        ColumnInfo("Target", lambda v: v.value),
    ]

    def __init__(self, matcher):
        super().__init__()
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
        self.ctab.set_columns(self.constraints_columns, self.matcher.constraints, self.matcher)
        self.vtab.set_columns(self.variables_columns, self.matcher.variables, self.matcher)

    def set_initial_values(self):
        self.check_mirror.setChecked(self.matcher.mirror_mode)

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
        self.check_mirror.clicked.connect(self.on_change_mirror)
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
        el   = self.matcher.elem_enum._values[0]
        elem = self.matcher.segment.elements[el]
        axis = self.matcher.lcon_enum._values[0]  # TODO: -> curve.y_name?
        pos  = elem.AT + elem.L
        value = self.matcher.segment.get_twiss(el, axis, pos)
        self.matcher.constraints.append(Constraint(
            elem, pos, axis, value))

    def add_variable(self):
        text, ok = QtGui.QInputDialog.getText(
            self.window(), "Add new variable", "Knob:")
        if ok and text:
            self.matcher.variables.append(
                variable_from_knob(self.matcher, text))

    def on_change_mirror(self, checked):
        # TODO: add/remove mirrored constraints (if untouched by the user)?
        self.matcher.mirror_mode = checked
