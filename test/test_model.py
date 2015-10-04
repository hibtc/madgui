# encoding: utf-8
"""
Tests for the model.Model runtime hierarchy.
"""

# tested classes
from cpymad.madx import CommandLog
from madgui.component.model import Model
from madgui.resource.file import FileResource

# utilities
import _compat

# standard library
import os
import sys
import unittest

__all__ = [
    'TestModel',
]


class TestModel(unittest.TestCase, _compat.TestCase):

    """
    Tests for the Model class.
    """

    # test configuration:

    path = os.path.join(os.path.dirname(__file__), 'data', 'lebt.cpymad.yml')

    # helper methods for tests:

    def load_model(self, path):
        """Load model with given name from specified path."""
        command_log = CommandLog(sys.stdout, 'X:> ')
        model = Model.load(self.path, command_log=command_log)
        model.madx.command.option(twiss_print=False)
        return model

    def setUp(self):
        self.model = self.load_model(self.path)

    def tearDown(self):
        del self.model

    # tests for Model API

    def test_compatibility_check(self):
        data = {
            'beam': {},
            'sequence': {},
        }
        with self.assertRaises(ValueError):
            Model(data=data, repo=None, madx=None)
        with self.assertRaises(ValueError):
            Model(data=dict(data, api_version=-1), repo=None, madx=None)
        with self.assertRaises(ValueError):
            Model(data=dict(data, api_version=2), repo=None, madx=None)
        Model(data=dict(data, api_version=1), repo=None, madx=None)

    def test_Model_API(self):
        """Check that the public Model attributes/methods behave reasonably."""
        model = self.model
        madx = model.madx
        # name
        self.assertEqual(model.name, 'lebt')
        # data
        repository = FileResource(self.path)
        self.assertEqual(model.data, repository.yaml())

    # tests for Sequence API

    def test_Sequence_API(self):
        """Check that the general Sequence API behaves reasonable."""
        sequence = self.model.sequence
        # name
        self.assertEqual(sequence.name, 's1')

    # def test_Sequence_twiss(self):        # see test_Optic_twiss for now
    # def test_Sequence_match(self):        # see test_Optic_match for now

    def test_Sequence_survey(self):
        """Execute survey() and check that it returns usable values."""
        survey = self.model.sequence.survey()
        # access some data to make sure the table was generated:
        s = survey['s']
        x = survey['x']
        y = survey['y']
        z = survey['z']

    # tests for Range API

    def test_Range_API(self):
        """Check that the general Range API behaves reasonable."""
        range = self.model.sequence.range
        # bounds
        self.assertEqual(range.bounds, ('#s', '#e'))
        # initial_conditions
        self.assertItemsEqual(range.initial_conditions.keys(), ['default'])
        # default_initial_conditions
        self.assertIs(range.default_initial_conditions,
                      range.initial_conditions['default'])

    def test_Range_twiss(self):
        """Execute twiss() and check that it returns usable values."""
        range = self.model.sequence.range
        twiss = range.twiss()
        # access some data to make sure the table was generated:
        betx = twiss['betx']
        bety = twiss['bety']
        alfx = twiss['alfx']
        alfy = twiss['alfy']

    def test_Range_match(self):
        """Execute match() and check that it returns usable values."""
        range = self.model.sequence.range
        knobs = range.match(
            constraints=[dict(range='sb', betx=0.3)],
            vary=['QP_K1'],
        )
        knobs['QP_K1']


if __name__ == '__main__':
    unittest.main()
