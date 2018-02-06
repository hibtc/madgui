"""
UI for matching.
"""

from pkg_resources import resource_filename

from madgui.qt import QtGui, uic
from madgui.widget.tableview import ColumnInfo, ExtColumnInfo
from madgui.correct.match import variable_from_knob, Constraint
from madgui.util.enum import make_enum


def get_constraint_elem(widget, c, i):
    return widget.elem_enum(c.elem.Name if c.elem else "(global)")

def set_constraint_elem(widget, c, i, name):
    if name is not None:
        el = widget.model.elements[str(name)]
        widget.matcher.constraints[i] = \
            Constraint(el, el.At+el.L, c.axis, c.value)

def get_constraint_axis(widget, c, i):
    return widget.lcon_enum(c.axis)

def set_constraint_axis(widget, c, i, axis):
    if axis is not None:
        value = widget.model.get_twiss(c.elem.Name, str(axis), c.pos)
        widget.matcher.constraints[i] = \
            Constraint(c.elem, c.pos, str(axis), value)

def set_constraint_value(widget, c, i, value):
    if value is not None:
        widget.matcher.constraints[i] = \
            Constraint(c.elem, c.pos, c.axis, value)

def get_knob_display(widget, v, i):
    return widget.knob_enum(format_knob(v.knob))

def set_knob_display(widget, v, i, text):
    if text is not None:
        knob = parse_knob(widget.model, str(text))
        if knob:
            widget.matcher.variables[i] = \
                variable_from_knob(widget.matcher, knob)

def format_knob(knob):
    return (knob.elem and
            "{}: {}".format(knob.elem.Name, knob.attr) or
            knob.param)

def parse_knob(model, text):
    if ':' in text:
        elem, attr = text.split(':')
    elif '->' in text:
        elem, attr = text.split('->')
    else:
        return None     # TODO
    elem = elem.strip()
    attr = attr.strip()
    return model.get_knob(model.elements[elem], attr)


class MatchWidget(QtGui.QWidget):

    ui_file = 'match.ui'

    constraints_columns = [
        ExtColumnInfo("Element", get_constraint_elem, set_constraint_elem,
                      resize=QtGui.QHeaderView.Stretch),
        ExtColumnInfo("Name", get_constraint_axis, set_constraint_axis,
                      resize=QtGui.QHeaderView.ResizeToContents),
        ExtColumnInfo("Target", 'value', set_constraint_value,
                      resize=QtGui.QHeaderView.ResizeToContents),
    ]

    variables_columns = [
        ExtColumnInfo("Knob", get_knob_display, set_knob_display,
                      resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("Initial", 'design',
                   resize=QtGui.QHeaderView.ResizeToContents),
        ColumnInfo("Final", lambda v: v.value,
                   resize=QtGui.QHeaderView.ResizeToContents),
    ]

    def __init__(self, matcher):
        super().__init__()
        uic.loadUi(resource_filename(__name__, self.ui_file), self)
        self.matcher = matcher
        self.model = model = matcher.model
        local_constraints = ['envx', 'envy'] + model.config['constraints']
        local_constraints = sorted(local_constraints)
        knob_names = [format_knob(knob) for knob in matcher.knobs]
        self.elem_enum = make_enum('Elem', model.el_names)
        self.lcon_enum = make_enum('Local', local_constraints, strict=False)
        self.knob_enum = make_enum('Knobs', knob_names, strict=False)
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
        self.ctab.set_columns(self.constraints_columns, self.matcher.constraints, self)
        self.vtab.set_columns(self.variables_columns, self.matcher.variables, self)

    def set_initial_values(self):
        self.check_mirror.setChecked(self.matcher.mirror_mode)

    def connect_signals(self):
        self.ctab.connectButtons(
            self.button_remove_constraint,
            self.button_clear_constraint)
        self.vtab.connectButtons(
            self.button_remove_variable,
            self.button_clear_variable)
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

    def on_update_constraints(self, *args):
        self.ctab.resizeColumnToContents(1)
        self.ctab.resizeColumnToContents(2)

    def on_update_variables(self, *args):
        self.vtab.resizeColumnToContents(1)
        self.vtab.resizeColumnToContents(2)

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
        el   = self.elem_enum._values[0]
        elem = self.model.elements[el]
        axis = self.lcon_enum._values[0]  # TODO: -> curve.y_name?
        pos  = elem.AT + elem.L
        value = self.model.get_twiss(el, axis, pos)
        self.matcher.constraints.append(Constraint(
            elem, pos, axis, value))

    def add_variable(self):
        self.matcher.variables.append(
            self.matcher.next_best_variable())

    def on_change_mirror(self, checked):
        # TODO: add/remove mirrored constraints (if untouched by the user)?
        self.matcher.mirror_mode = checked
