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
        repository = FileResource(self.path)
        self.assertEqual(model.data, repository.yaml())


if __name__ == '__main__':
    unittest.main()
