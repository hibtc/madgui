# encoding: utf-8
"""
UI for matching.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from pkg_resources import resource_filename

from madqt.qt import QtGui, uic
from madqt.widget.tableview import ColumnInfo


class MatchWidget(QtGui.QWidget):

    ui_file = 'match.ui'

    constraints_columns = [
        ColumnInfo("Element", lambda c: c.elem['name']),
        ColumnInfo("Name", 'axis'),
        ColumnInfo("Target", 'value'),
    ]

    variables_columns = [
        ColumnInfo("Element", lambda v: v.elem['name']),
        ColumnInfo("Expression", 'expr'),
        ColumnInfo("Design", 'design'),
        ColumnInfo("Target", lambda v: v.elem[v.attr]),
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
        self.matcher.constraints.update_after.connect(self.on_update_constraints)
        self.matcher.variables.update_after.connect(self.on_update_variables)

    def selection_changed_constraints(self):
        self.button_remove_constraint.setEnabled(bool(self.ctab.selectedIndexes()))

    def selection_changed_variables(self):
        self.button_remove_variable.setEnabled(bool(self.vtab.selectedIndexes()))

    def on_update_constraints(self, *args):
        self.button_clear_constraint.setEnabled(bool(self.matcher.constraints))

    def on_update_variables(self, *args):
        self.button_clear_variable.setEnabled(bool(self.matcher.variables))
