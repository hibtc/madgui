"""
UI for matching.
"""

from madgui.qt import QtGui, load_ui
from madgui.core.unit import ui_units
from madgui.widget.tableview import ColumnInfo
from madgui.correct.match import variable_from_knob, Constraint
from madgui.util.enum import make_enum


Button = QtGui.QDialogButtonBox


def get_constraint_elem(cell):
    widget, c = cell.context, cell.data
    return widget.elem_enum(c.elem.node_name if c.elem else "(global)")

def set_constraint_elem(cell, name):
    widget, c, i = cell.context, cell.data, cell.row
    if name is not None:
        el = widget.model.elements[str(name)]
        widget.matcher.constraints[i] = \
            Constraint(el, el.position+el.length, c.axis, c.value)

def get_constraint_axis(cell):
    widget, c = cell.context, cell.data
    return widget.lcon_enum(c.axis)

def set_constraint_axis(cell, axis):
    widget, c, i = cell.context, cell.data, cell.row
    if axis is not None:
        value = widget.model.get_twiss(c.elem.node_name, str(axis), c.pos)
        widget.matcher.constraints[i] = \
            Constraint(c.elem, c.pos, str(axis), value)

def get_constraint_unit(cell):
    c = cell.data
    return ui_units.label(c.axis, c.value)

def set_constraint_value(cell, value):
    widget, c, i = cell.context, cell.data, cell.row
    if value is not None:
        widget.matcher.constraints[i] = \
            Constraint(c.elem, c.pos, c.axis, value)

def get_knob_display(cell):
    widget, v = cell.context, cell.data
    return widget.knob_enum(v.knob)

def set_knob_display(cell, text):
    widget, i = cell.context, cell.row
    if text is not None:
        knob = parse_knob(widget.model, str(text))
        if knob:
            widget.matcher.variables[i] = \
                variable_from_knob(widget.matcher, knob)


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
        ColumnInfo("Element", get_constraint_elem, set_constraint_elem,
                   resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("Name", get_constraint_axis, set_constraint_axis,
                   resize=QtGui.QHeaderView.ResizeToContents),
        ColumnInfo("Target", 'value', set_constraint_value, convert='axis',
                   resize=QtGui.QHeaderView.ResizeToContents),
        ColumnInfo("Unit", get_constraint_unit,
                   resize=QtGui.QHeaderView.ResizeToContents),
    ]

    variables_columns = [
        ColumnInfo("Knob", get_knob_display, set_knob_display,
                   resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("Initial", 'design',
                   resize=QtGui.QHeaderView.ResizeToContents),
        ColumnInfo("Final", 'value',
                   resize=QtGui.QHeaderView.ResizeToContents),
    ]

    def __init__(self, matcher):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
        self.matcher = matcher
        self.model = model = matcher.model
        local_constraints = ['envx', 'envy'] + model.config['constraints']
        local_constraints = sorted(local_constraints)
        self.elem_enum = make_enum('Elem', model.el_names)
        self.lcon_enum = make_enum('Local', local_constraints, strict=False)
        self.knob_enum = make_enum('Knobs', matcher.knobs, strict=False)
        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    # The three steps of UI initialization

    def init_controls(self):
        self.ctab.header().setHighlightSections(False)
        self.vtab.header().setHighlightSections(False)
        self.ctab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.vtab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.ctab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.vtab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.ctab.set_columns(self.constraints_columns, self.matcher.constraints, self)
        self.vtab.set_columns(self.variables_columns, self.matcher.variables, self)

    def set_initial_values(self):
        self.check_mirror.setChecked(self.matcher.mirror_mode)
        self.update_buttons()

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
        self.buttonBox.button(Button.Ok).clicked.connect(self.accept)
        self.buttonBox.button(Button.Reset).clicked.connect(self.matcher.reset)
        self.button_match.clicked.connect(self.matcher.match)
        self.check_mirror.clicked.connect(self.on_change_mirror)
        # TODO: connect self.matcher.finished?

    def on_update_constraints(self, *args):
        self.ctab.resizeColumnToContents(1)
        self.ctab.resizeColumnToContents(2)
        self.update_buttons()

    def on_update_variables(self, *args):
        self.vtab.resizeColumnToContents(1)
        self.vtab.resizeColumnToContents(2)
        self.update_buttons()

    def update_buttons(self):
        num_vars = len(self.matcher.variables)
        num_cons = len(self.matcher.constraints)
        # TODO: the last condition should be relaxed when we support methods
        # other than LMDIF:
        self.button_match.setEnabled(
            num_vars > 0 and
            num_cons > 0 and
            num_vars == num_cons)

    def showEvent(self, event):
        self.matcher.start()

    def hideEvent(self, event):
        self.matcher.stop()

    def accept(self):
        self.matcher.apply()
        self.window().accept()

    def add_constraint(self):
        el   = self.elem_enum._values[0]
        elem = self.model.elements[el]
        axis = self.lcon_enum._values[0]  # TODO: -> curve.y_name?
        pos  = elem.position + elem.length
        value = self.model.get_twiss(el, axis, pos)
        self.matcher.constraints.append(Constraint(
            elem, pos, axis, value))

    def add_variable(self):
        self.matcher.variables.append(
            self.matcher.next_best_variable())

    def on_change_mirror(self, checked):
        # TODO: add/remove mirrored constraints (if untouched by the user)?
        self.matcher.mirror_mode = checked
